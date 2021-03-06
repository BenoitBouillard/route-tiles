// Warn if overriding existing method
if(Array.prototype.equals)
    console.warn("Overriding existing Array.prototype.equals. Possible causes: New API defines the method, there's a framework conflict or you've got double inclusions in your code.");
// attach the .equals method to Array's prototype to call it on any array
Array.prototype.equals = function (array) {
    // if the other array is a falsy value, return
    if (!array)
        return false;

    // compare lengths - can save a lot of time
    if (this.length != array.length)
        return false;

    for (var i = 0, l=this.length; i < l; i++) {
        // Check if we have nested arrays
        if (this[i] instanceof Array && array[i] instanceof Array) {
            // recurse into the nested arrays
            if (!this[i].equals(array[i]))
                return false;
        }
        else if (this[i] != array[i]) {
            // Warning - two different object instances will never be equal: {x:20} != {x:20}
            return false;
        }
    }
    return true;
}
// Hide method from for-in loops
Object.defineProperty(Array.prototype, "equals", {enumerable: false});


$(document).ready(function(){

    // Add collapse indicator for sections
    $('h3').each(function(){
        $('<svg class="collapse-indicator" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg"><path fill-rule="evenodd" clip-rule="evenodd" fill="none" stroke-linecap="round" d="M6.25 2.5 l7.5 7.5 l-7.5 7.5" /></svg>').prependTo($(this))
    })

    $.i18n(/*{locale:'en'}*/).load({
        'en': 'i18n/en.json',
        'fr': 'i18n/fr.json'
    }).done( function(){
        let storage_locale = localStorage.getItem('locale')
        if (storage_locale) {
            let val = $("#switch-locale").find('option[data-locale="'+storage_locale+'"]').val();
            $("#switch-locale").val(val);
            $.i18n().locale = storage_locale;
        }

        $('#switch-locale').on('change', function(e){
            e.preventDefault();
            localStorage.setItem('locale', $(this).find(':selected').data('locale'));
            $.i18n().locale = $(this).find(':selected').data('locale');
            $('body').i18n();
        })
        $('body').i18n();

        min = function(a,b) {
            if (a>b) return b;
            return a;
        }

        max = function(a,b) {
            if (a>b) return a;
            return b;
        }

        var Tile = L.Rectangle.extend({
            options: {
                tile_id: 0
            },

            initialize: function (latlngs, options) {
                L.Rectangle.prototype.initialize.call(this, latlngs, options);
                this.selected = false;
                this.highlighted = false;
                this.iserror = false
            },
            update: function() {
                let opacity = 0;
                let fill_color = this.options.color;
                if (this.iserror) {
                    opacity = 0.7;
                    fill_color = "orange";
                }
                if (this.selected) opacity += 0.2;
                if (this.highlighted) opacity += 0.1;
                this.setStyle({fillOpacity:opacity, fillColor:fill_color});
            },

            error: function(level) {
                this.iserror = level;
                this.update();
            },
            highlight: function(level) {
                this.highlighted = level;
                this.update();
            },
            select: function(level) {
                this.selected = level;
                this.update();
            },

        });

        tile = function (id, options) {
            return new Tile(id, options);
        };


        var mymap = L.map('mapid', {zoomSnap: 0.5, zoomDelta: 0.5, wheelPxPerZoomLevel:100, wheelDebounceTime:20});
        var routePolyline = false;
        var actualTrace = false;

        var tilesLayerGroup = L.layerGroup().addTo(mymap);

        function TileFromCoord(lat, lon) {
            let n = Math.pow(2,14);
            let x = Math.floor(n * (lon + 180 ) / 360);
            let lat_r = lat*Math.PI/180;
            let y = Math.floor(n * ( 1 - ( Math.log( Math.tan(lat_r) + 1/Math.cos(lat_r) ) / Math.PI ) ) / 2);
            return [x, y];
        }

        function TileIdFromLatLng(latlon) {
            let ll = TileFromCoord(latlon.lat, latlon.lng)
            return ll[0] + "_" + ll[1]
        }

        function LatLngFromTile(x, y) {
            let n = Math.pow(2,14);
            let lat = Math.atan( Math.sinh( Math.PI * (1 - 2*y / n ) ) ) * 180.0 / Math.PI;
            let lon = x / n * 360.0 - 180.0;
            return L.latLng(lat, lon);
        }

        function boundsFromTile(x, y) {
            return L.latLngBounds(LatLngFromTile(x, y), LatLngFromTile(x+1, y+1));
        }

        function boundsFromTileId(tileId) {
            let part = tileId.split('_')
            let x = parseInt(part[0])
            let y = parseInt(part[1])
            return boundsFromTile(x, y)
        }

        var displayed_tiles = new Map();
        var selected_tiles = []
        var visited_tiles = []
        var routes_visited_tiles = []
        var error_tiles = []


        function updateMapTiles(e) {
            if (mymap.getZoom()<10) {
                // Remove tiles
                displayed_tiles.clear();
                tilesLayerGroup.clearLayers();
            } else {
                // display tiles
                let bounds = mymap.getBounds();
                let t1 = TileFromCoord(bounds.getNorth(), bounds.getWest())
                let t2 = TileFromCoord(bounds.getSouth(), bounds.getEast())
                for (let x=min(t1[0], t2[0]); x<max(t1[0], t2[0])+1; x++) {
                    for (let y=min(t1[1], t2[1]); y<max(t1[1], t2[1])+1; y++) {
                        let tile_id = x + "_" + y
                        if (!displayed_tiles.has(tile_id)) {
                            let color = 'blue';
                            let weight = 0.1;
                            let opacity = 0;
                            if (!visited_tiles.includes(tile_id)) {
                                color = 'red';
                                weight = 1.0;
                            }
                            if (routes_visited_tiles.includes(tile_id)) {
                                opacity = 0.3;
                            }
                            let tile_rect = tile(boundsFromTile(x, y), {color: color, fillColor: color, fillOpacity:opacity, weight:weight, tile_id:tile_id}).addTo(tilesLayerGroup);
                            displayed_tiles.set(tile_id, tile_rect);
                            if (selected_tiles.includes(tile_id)) {
                                tile_rect.select(1)
                            }
                            if (error_tiles.includes(tile_id)) {
                                tile_rect.error(1)
                            }
                        } else {
                            let tile = displayed_tiles.get(tile_id)
                            if (selected_tiles.includes(tile_id)) {
                                tile.select(1);
                            } else {
                                tile.select(0);
                            }
                        }
                    }
                }
            }
        }
        mymap.setView(JSON.parse(localStorage.getItem("map_center")) || [48.85, 2.35],
                      JSON.parse(localStorage.getItem("map_zoom")) || 10);
        mymap.on("moveend", function() {
            localStorage.setItem("map_zoom", JSON.stringify(mymap.getZoom()))
            localStorage.setItem("map_center", JSON.stringify(mymap.getCenter()))
            updateMapTiles();
        });
        mymap.on("load", updateMapTiles);

        mymap.on("click", function(e) {
            if (!$('#alert-split').hasClass("d-none")) return;
            if (selectLoc!=false) return;
            if (mymap.getZoom()>=10) {
                let tile_id = TileIdFromLatLng(e.latlng)
                let tile = displayed_tiles.get(tile_id)
                if (selected_tiles.includes(tile_id)) {
                    selected_tiles.splice(selected_tiles.indexOf(tile_id), 1);
                    tile.select(0);
                } else {
                    selected_tiles.push(tile_id);
                    tile.select(1);
                }
                localStorage.setItem("selected_tiles", JSON.stringify(selected_tiles));

                request_route();
            }
        });

        L.tileLayer('https://api.mapbox.com/styles/v1/{id}/tiles/{z}/{x}/{y}?access_token=pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpejY4NXVycTA2emYycXBndHRqcmZ3N3gifQ.rJcFIG214AriISLbB6B5aw', {
            maxZoom: 18,
            attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a> contributors, ' +
                '<a href="https://creativecommons.org/licenses/by-sa/2.0/">CC-BY-SA</a>, ' +
                'Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
            id: 'mapbox/streets-v11'
        }).addTo(mymap);

        function latlonToStr(ll) {
          return ll.lat + ","+ ll.lng;
        }
        function latlonToQuery(ll) {
          return  [ll.lat, ll.lng];
        }

        var routeId="";
        var timeoutID=false;
        var active_timeout = 0;
        var route_rq_id = 0;
        var sessionId = false;
        var state = false;

        function setMessageAlert(level) {
            $("#progress-message").removeClass(function(index, className){
                return (className.match(/(^|\s)alert-\S+/g)||[]).join('')
            }).addClass('alert-'+level);
        }

        function route_status(timeout_id) {
            if (timeout_id != active_timeout) return;
            $.getJSON({
                url: 'route_status',
                data: { 'sessionId': sessionId, 'findRouteId' : routeId },
                success: function ( data ) {
                    if (data['status']=="OK") {
                        state = data['state']
                        $("#message").text($.i18n("message-state-"+data['state']));
                        if ('route' in data) {
                            routeId = data['findRouteId']
                            if (!routePolyline) {
                                routePolyline = L.polyline(data.route, {color: '#FF0000', opacity:0.8}).addTo(mymap);
                            } else {
                                routePolyline.setLatLngs(data.route).bringToFront();
                            }
                            $("#length").text(parseFloat(data['length']).toFixed(2)+" km");
                        }
                        if (data['state']!='complete') {
                            timeoutID = window.setTimeout(route_status, 1000, ++active_timeout);
                        } else {
                            setMessageAlert('success');
                            $("#spinner-searching").hide();
                            $("#button-download-route").show();
                            timeoutID = false;
                            actualTrace =  {distance: data.length, route: data.route, polyline: routePolyline};
                            $('button#addTrace').prop("disabled", false);
                        }
                    } else {
                        $("#message").text($.i18n("message-state-fail")+":"+$.i18n("msg-error_"+data['error_code']));
                        setMessageAlert('danger');
                        $("#length").text("");
                        error_tiles = data.error_args;
                        for (let i=0; i<error_tiles.length; i++) {
                            let tile = displayed_tiles.get(error_tiles[i])
                            tile.error(1);
                        }
                        $("#spinner-searching").hide();
                        timeoutID = false;
                    }

                }
            });
        };

        { // CONFIG-STORAGE
            $('select.config-storage').each(function(){
                let id = this.id;
                let storage = localStorage.getItem(id)
                if (storage) {
                    let val = $(this).find('option[data-value="'+storage+'"]').val();
                    $(this).val(val);
                }

                $(this).on('change', function(e) {
                    e.preventDefault();
                    $(this).data('value', $(this).find(':selected').data('value'));
                    localStorage.setItem(this.id, $(this).find(':selected').data('value'));
                });
            });

            $('input[type="text"].config-storage,input[type="number"].config-storage').each(function(){
                let id = this.id;
                $(this).val(localStorage.getItem(id) || "");

                $(this).on('change', function(e) {
                    e.preventDefault();
                    localStorage.setItem(this.id, $(this).val());
                });
            });

            $('input[type="checkbox"].config-storage').each(function(){
                let id = this.id;
                $(this).prop('checked', (localStorage.getItem(id) || "true") == "true");

                $(this).on('change', function(e) {
                    e.preventDefault();
                    localStorage.setItem(this.id, this.checked);
                });
            });

            $('.request-route').on("change", function() {
                request_route();
            });
        } // CONFIG-STORAGE

        function start_route(timeout_id) {
            if (timeout_id != active_timeout) return;
            $('button#addTrace').prop("disabled", true);
            actualTrace = false;
            setMessageAlert('info');
            $("#message").text($.i18n("message-state-ask-route"));
            $("#length").text("");
            $("#spinner-searching").show();
            let data = { 'sessionId'      : sessionId,
                         'start'          : latlonToQuery(markers['start'].getLatLng()),
                         'turnaroundCost':$("#turnaround-cost").find(':selected').data('value') }
            if ('end' in markers) {
                data['end'] = latlonToQuery(markers['end'].getLatLng());
            }
            else {
                data['end'] = data['start'];
            }
            data['waypoints'] = []
            waypoints.forEach(function(wp) {
                data['waypoints'].push(latlonToQuery(wp.getLatLng()))
            });
            data['tiles'] = selected_tiles
            data['mode'] = $('#mode-selection').find(':selected').data('value')

            $.getJSON({
                url: 'start_route',
                data: data,
                success: function ( data ) {
                    sessionId = data.sessionId
                    if (data['status']=="OK") {
                        for (let i=0; i<error_tiles.length; i++) {
                            let tile = displayed_tiles.get(error_tiles[i])
                            tile.error(0);
                        }
                        error_tiles = []
                        route_status(timeout_id);
                    } else {
                        setMessageAlert('danger');
                        $("#message").text($.i18n("message-state-fail")+":"+data['message']);
                        $("#length").text("");
                        error_tiles = data.tiles;
                        for (let i=0; i<error_tiles.length; i++) {
                            let tile = displayed_tiles.get(error_tiles[i])
                            tile.error(1);
                        }

                        //updateMapTiles();
                    }
                }
            });
        }
        function request_route() {
            console.log("Request_route")
            console.log(selected_tiles);
            if (timeoutID) {
                window.clearTimeout(timeoutID);
                timeoutID = false;
            }
            if (!('start' in markers)) return;
            if (!('end' in markers) && selected_tiles.length==0 && waypoints.length==0) return;
            setMessageAlert('info');
            $("#button-download-route").hide();
            $("#message").text($.i18n("message-state-wait"));
            $("#length").text("");

            timeoutID = window.setTimeout(start_route, 2000, ++active_timeout);
        }

        { // STATSHUNTERS

            var maxSquareLayer = false;
            var clusterLayer = false;

            function statshunters_request(request) {
                $.ajax({
                    type: 'GET',
                    url: request,
                    data: {url: $("#statshunters_url").val(), filter:$("#statshunters_filter").val()},
                    success: function ( data ) {
                        if (data.status=="OK") {
                            if (maxSquareLayer) {
                                maxSquareLayer.remove();
                                maxSquareLayer = false;
                            }
                            if (clusterLayer) {
                                clusterLayer.remove()
                                clusterLayer = false;
                            }
                            visited_tiles = data.tiles
                            displayed_tiles.clear();
                            tilesLayerGroup.clearLayers();
                            updateMapTiles();
                            clusterLayer = omnivore.kml.parse(data.cluster)
                            clusterLayer.setStyle({
                                color: '#20ff2080',
                                weight: 3
                            });
                            if ($('#showCluster').is(":checked")) {
                                clusterLayer.addTo(mymap)
                            }
                            maxSquareLayer = omnivore.kml.parse(data.maxSquare)
                            maxSquareLayer.setStyle({
                                color: '#2020FF80',
                                weight: 3
                            });
                            if ($('#showMaxSquare').is(":checked")) {
                                maxSquareLayer.addTo(mymap)
                            }
                        }
                        else {
                            alert(data.message);
                        }
                    }
                });
            }

            $( 'button#bImportStatsHunters' ).click(function ( e ) {
                statshunters_request('statshunters');
                e.preventDefault();
            });

            $("#statshunters_filter").on("change",  function ( e ) {
                statshunters_request('statshunters_filter');
                e.preventDefault();
            });

            {
                /*let statshunters_filter = localStorage.getItem("statshunters_filter")
                if (statshunters_filter) {
                    $("#statshunters_filter").val(statshunters_filter);
                }
                let statshunters_url = localStorage.getItem("statshunters_url")
                if (statshunters_url) {
                    $("#statshunters_url").val(statshunters_url);

                }*/
                if ($("#statshunters_url").val()!="") {
                    statshunters_request('statshunters_filter');
                }
            }
            $("#bImportStatsHuntersReset").click(function() {
                localStorage.removeItem("statshunters_filter");
                localStorage.removeItem("statshunters_url");
                if (maxSquareLayer) {
                    maxSquareLayer.remove();
                    maxSquareLayer = false;
                }
                if (clusterLayer) {
                    clusterLayer.remove()
                    clusterLayer = false;
                }
                $("#statshunters_filter").val("");
                $("#statshunters_url").val("");
                visited_tiles = [];
                displayed_tiles.clear();
                tilesLayerGroup.clearLayers();
                updateMapTiles();
            });

            $('#showCluster').on("change", function(e) {
                if (clusterLayer) {
                    if (this.checked) {
                      mymap.addLayer(clusterLayer)
                    }
                    else {
                      mymap.removeLayer(clusterLayer)
                    }
                }
            });
            $('#showMaxSquare').on("change", function(e) {
                if (maxSquareLayer) {
                    if (this.checked) {
                      mymap.addLayer(maxSquareLayer)
                    }
                    else {
                      mymap.removeLayer(maxSquareLayer)
                    }
                }
            });
        } // STATSHUNTERS

        var selectLoc = false;
        var markers = {};
        var waypoints = [];

        var markersIcons = {
          start: L.ExtraMarkers.icon({
             icon: 'fa-play-circle',
             markerColor: 'green',
             shape: 'circle',
             prefix: 'fas'
         }),
          end: L.ExtraMarkers.icon({
             icon: 'fa-stop-circle',
             markerColor: 'orange-dark',
             shape: 'circle',
             prefix: 'fas'
         }),
          waypoint: L.ExtraMarkers.icon({
             icon: 'fa-dot-circle',
             markerColor: 'cyan',
             shape: 'circle',
             prefix: 'fas'
         }),

        }

        $("button#bStart").on("click", function(e) {
            selectLoc = "start";
        });
        $("button#bEnd").on("click", function(e) {
            selectLoc = "end";
        });

        $("button#addWaypoint").on("click", function(e) {
            selectLoc = "waypoint";
        });

        $("button#bClearStart").on("click", function(e) {
            selectLoc = false;
            if ("start" in markers) {
                markers["start"].remove();
                delete markers["start"];
                localStorage.removeItem("start");
            }
        });
        $("button#bClearEnd").on("click", function(e) {
            selectLoc = false;
            if ("end" in markers) {
                markers["end"].remove();
                delete markers["end"];
                localStorage.removeItem("end");
                request_route();
            }
        });
        $("button#clear-tiles").on("click", function(e) {
            selected_tiles = [];
            localStorage.setItem("selected_tiles", JSON.stringify(selected_tiles));
            updateMapTiles();

            waypoints.forEach(function(wp) {
                wp.remove();
            });
            waypoints = [];
            store_waypoints();

            request_route();
    });

        $("#gpxMessage").hide();

        $("#button-download-route").on("click", function(e) {
           file_name = prompt("File name", "")
           if (file_name!=null) {
               $("#gpxMessage").hide();
               $.getJSON({
                   url: 'generate_gpx',
                   data: { 'sessionId': sessionId, name : file_name },
                   success: function ( data ) {
                       if (data.status!="OK") {
                           $("#gpxMessage").text(data.message).show();
                       }
                       else {
                          $("a#gpxDownload").attr("href", data.path);
                          $("a#gpxDownload")[0].click();
                       }
                   }
               });
           }
        });

        $("button#bRevert").on("click", function(e) {
            let startPos =  markers["start"].getLatLng();
            let endPos =  markers["end"].getLatLng();
            markers["start"].setLatLng(endPos);
            markers["end"].setLatLng(startPos);
            let latlng = markers["start"].getLatLng();
            localStorage.setItem("start", latlng.lat+","+latlng.lng);
            latlng = markers["end"].getLatLng();
            localStorage.setItem("end", latlng.lat+","+latlng.lng);
            request_route();
            update_circle();
        });

        var circle_layer = false;

        function update_circle() {
            if (circle_layer) {
                if (($('#is-draw-circle').is(":checked")) && ("start" in markers) && (!isNaN(parseInt($('#circle-size')))))
                {
                    circle_layer.setRadius(1000*parseInt($('#circle-size').val()));
                    circle_layer.setLatLng(markers["start"].getLatLng());
                } else {
                    circle_layer.remove();
                    circle_layer = false;

                }
            } else if (($('#is-draw-circle').is(":checked")) && ("start" in markers) && (!isNaN(parseInt($('#circle-size'))))) {
                circle_layer = L.circle(markers["start"].getLatLng(), {radius: 1000*parseInt($('#circle-size').val()), fill: false}).addTo(mymap);
            }
        }

        $('#is-draw-circle,#circle-size').on("change", function() {
            update_circle();
        })

        function add_marker(name, latlng) {
            if ((name in markers) && markers[name]) {
                markers[name].setLatLng(latlng);
            } else {
                markers[name] =  L.marker(latlng, {draggable: true, title: name, icon: markersIcons[name]}).addTo(mymap).on("dragend", function(e){
                    localStorage.setItem(this.options.title, this.getLatLng().lat+","+this.getLatLng().lng);
                    request_route();
                });
            }
        }

        function store_waypoints() {
            wps = []
            waypoints.forEach(function(wp) {
                wps.push(latlonToQuery(wp.getLatLng())  )
            })
            localStorage.setItem("waypoints", JSON.stringify(wps))
        }


        function add_waypoint(latlng) {
            waypoints.push(L.marker(latlng, {draggable: true, title: "waypoint", icon: markersIcons['waypoint']}).addTo(mymap).on("dragend", function(e){
                //localStorage.setItem(this.options.title, this.getLatLng().lat+","+this.getLatLng().lng);
                request_route();
                store_waypoints();
            }).on("click", function(e) {
                e.target.remove();
                waypoints.splice(waypoints.indexOf(e.target), 1);
                request_route();
                store_waypoints();
            }));
            store_waypoints();
        }

        (JSON.parse(localStorage.getItem("waypoints")) || []).forEach(function(wp){
            add_waypoint(wp)
        })


        mymap.on("click", function (e) {
            if (selectLoc==false) return;
            if (selectLoc=="waypoint") {
                add_waypoint(e.latlng);
            } else {
                add_marker(selectLoc, e.latlng);
                update_circle();
                localStorage.setItem(selectLoc, e.latlng.lat+","+e.latlng.lng);
            }
            selectLoc = false;
            request_route();
        });


        { // local Storage recovery
            function load_marker(name) {
                let lcs = localStorage.getItem(name)
                if (lcs) {
                    add_marker(name, lcs.split(','));
                }
            }
            load_marker("start");
            load_marker("end");
            update_circle();

            try {
                selected_tiles = JSON.parse(localStorage.getItem("selected_tiles")) || []
            } catch(e) {
                if (typeof localStorage.getItem("selected_tiles")=='string') {
                    selected_tiles = localStorage.getItem("selected_tiles").split(",");
                } // COMPATIBILITY
            }

            updateMapTiles();

            request_route();
        }

        {
            var traces = [];

            function filter_traces() {
                var filter = ""
                if ($("#filter-activated").is(":checked")) {
                    filter = localStorage.getItem("filterField")
                }
                const regex = new RegExp(filter);
                traces.forEach(function(trace) {
                    if (regex.test(trace.name)) {
                        if (trace.hmi.is(":hidden")) {
                            trace.hmi.show();
                            trace.polyline.setStyle({color:'green'})
                        }
                    } else {
                        if (trace.hmi.is(":visible")) {
                            if (trace.hmi.hasClass("active")) {
                                trace.hmi.removeClass("active");
                                $('.action_on_trace').prop("disabled", true);
                            }
                            trace.hmi.hide();
                            trace.polyline.setStyle({color:'rgba(0,0,0,0)'})
                        }
                    }
                })
            }

            var undo_list = []
            $('#button-undo').prop("disabled", true);

            function refresh_localstorage_traces() {
                if (undo_list.push(localStorage.getItem("traces"))>10) {
                   undo_list.shift();
                }
                $('#button-undo').prop("disabled", false);

                localStorage.setItem("traces", JSON.stringify(traces, ['name', 'distance', 'route']));
            }

            $('#button-undo').on('click', function() {
                undo_traces = undo_list.pop();
                if (undo_list.length==0) {
                    $('#button-undo').prop("disabled", true);
                }
                localStorage.setItem("traces", undo_traces);
                load_localStorage_traces();
            });

            function gen_trace_hmi(trace) {
                trace.hmi = $('<a href="#" class="list-group-item list-group-item-action"><span>'+trace.name+'</span><span class="badge badge-light" style="float:right;">'+trace.distance.toFixed(2)+' km</span></a>')
                return trace.hmi
            }

            function update_trace(trace) {
                trace.hmi.find('span.badge').text(trace.distance.toFixed(2)+" km")
                trace.polyline.setLatLngs(trace.route);
            }


            function load_localStorage_traces() { // ROUTES localStorage
                // Clean
                traces.forEach(function(trace) {
                    trace.polyline.remove();
                });
                $("#traces-list").empty();

                traces = JSON.parse(localStorage.getItem("traces")) || []
                // Compatibility
                if (traces.length==0 && localStorage.getItem("trace_count")) {
                    let trace_count = parseInt(localStorage.getItem("trace_count") || "0");
                    for (let trace_val=0; trace_val<trace_count; trace_val++) {
                        let coords = localStorage.getItem('trace'+trace_val+'_coords').split(",").map(x => x.split(" ").map(v => parseFloat(v)));
                        let name = localStorage.getItem('trace'+trace_val+'_name');
                        let dist = parseFloat(localStorage.getItem('trace'+trace_val+'_length'));
                        traces.push({name: name, distance: dist, route: coords})
                    }
                    refresh_localstorage_traces();
                    for (let trace_val=0; trace_val<trace_count; trace_val++) {
                        localStorage.removeItem('trace'+trace_val+'_coords');
                        localStorage.removeItem('trace'+trace_val+'_name');
                        localStorage.removeItem('trace'+trace_val+'_length');
                    }
                    localStorage.removeItem('trace_count');
                }
                traces.forEach(function(trace) {
                    if (isNaN(trace.distance)) { // Compatibility
                        trace.distance = parseFloat(trace.distance)
                    }
                    gen_trace_hmi(trace).appendTo('#traces-list')
                    trace.polyline = L.polyline(trace.route, {color: 'green', opacity:0.8}).addTo(mymap);
                });
                filter_traces();
            }

            load_localStorage_traces();

            $('#filter-activated,input#filterField').on("change", function(e) {
                filter_traces();
            })

            $('button#addTrace').on("click", function(e) {
                if ($('#show-tiles').is(':checked')) {
                    for (const latlng of routePolyline.getLatLngs()) {
                        const tile_id = TileIdFromLatLng(latlng);
                        if (! routes_visited_tiles.includes(tile_id)) {
                            routes_visited_tiles.push(tile_id);
                            if (displayed_tiles.has(tile_id)) {
                                const tile = displayed_tiles.get(tile_id);
                                tile.highlight(true);
                            }
                        }
                    }
                }

                actualTrace.name = $('#traceName').val();
                gen_trace_hmi(actualTrace).appendTo('#traces-list')
                actualTrace.polyline.setStyle({color:'green'});
                traces.push(actualTrace)
                actualTrace = false
                $('button#addTrace').prop("disabled", true);
                routePolyline = false;
                refresh_localstorage_traces();
            });

            $('button#addTrace').prop("disabled", true);
            $('.action_on_trace').prop("disabled", true);

            $('div#traces-list').on('click', 'a', function(e) {
                if ($('.alert-dismissible:not(.d-none)').length > 0) return
                e.preventDefault();

                let previous_pos = $('div#traces-list>.active').index();
                let pos = $(this).index();
                if (previous_pos>=0) {
                    traces[previous_pos].polyline.setStyle({color:'green'});
                    $('div#traces-list>.active').removeClass('active');
                    $('.action_on_trace').prop("disabled", true);
                }
                if (pos != previous_pos) {
                    $(this).addClass('active');
                    traces[pos].polyline.setStyle({color:'blue'}).bringToFront();
                    $('.action_on_trace').prop("disabled", false);
                }
            });



            $('#remove-trace').on('click', function(e) {
                let pos = $('div#traces-list>.active').index();
                if (pos>=0) {
                    traces[pos].polyline.remove();
                    traces.splice(pos, 1);
                    $('div#traces-list>.active').remove();
                    refresh_localstorage_traces();
                    $('.action_on_trace').prop("disabled", true);
                }
            });

            $('#duplicate-trace').on('click', function(e) {
                let pos = $('div#traces-list>.active').index();
                if (pos>=0) {
                    const selTrace = traces[pos]
                    var newTrace =  {name: selTrace.name, distance: selTrace.distance, route: selTrace.route};
                    gen_trace_hmi(newTrace).appendTo('#traces-list')
                    newTrace.polyline = L.polyline(newTrace.route, {color: 'green', opacity:0.8}).addTo(mymap);
                    traces.push(newTrace)
                    refresh_localstorage_traces();
                }
            });

            $('div#traces-list').on("mouseenter", 'a.active', function() {
                $('div#traces-list>.active').popover('show');
            }).on( "mouseleave", 'a.active', function() {
                setTimeout(function() {
                  if (!$(".popover:hover").length) {
                    $('div#traces-list>.active').popover('hide');
                  }
                }, 300);
            });

            $('.alert-dismissible button.close').on('click', function(e) {
                $(this).parent('.alert-dismissible').addClass("d-none");
            });

            // MERGE

            $('#merge-trace').on('click', function(e) {
                $('#alert-merge').removeClass("d-none");
            });

            $('div#traces-list').on('click', 'a', function(e) {
                let previous_pos = $('div#traces-list>.active').index();
                let pos = $(this).index();
                if (!$('#alert-merge').hasClass('d-none')) {
                    e.preventDefault();
                    if (pos != previous_pos) {
                        traces[previous_pos].route.push(...traces[pos].route)
                        traces[previous_pos].distance = traces[previous_pos].distance + traces[pos].distance
                        //traces[previous_pos].polyline.remove()
                        traces.splice(pos, 1);
                        $(this).remove();
                        update_trace(traces[previous_pos]);
                        refresh_localstorage_traces();
                    }
                    $('#alert-merge').addClass('d-none');
                }
            });

            $('#progress-message').on('click', function(e) {
                if (!$('#alert-merge').hasClass("d-none")) {
                    var trace = traces[$('div#traces-list>.active').index()]
                    trace.route.push(...actualTrace.route)
                    trace.distance += actualTrace.distance
                    update_trace(trace);
                    refresh_localstorage_traces();
                    $('#alert-merge').addClass("d-none");
                }
            });


            // INSERT

            $('#insert-trace').on('click', function(e) {
                $('#alert-insert').removeClass("d-none");
            });

            function insert_trace(trace1, trace2) {
                const pos_start = trace1.route.findIndex((elt) => elt.equals(trace2.route[0]))
                const pos_end = trace1.route.findIndex((elt) => elt.equals(trace2.route[trace2.route.length - 1]), pos_start)
                if ((pos_start == -1) || ( pos_end== -1))  return false
                const rm_part = trace1.route.slice(pos_start, pos_end)
                trace1.route = trace1.route.slice(0, pos_start).concat(trace2.route).concat(trace1.route.slice(pos_end))
                trace1.distance += trace2.distance - compute_distance(rm_part)
                return true
            }

            $('div#traces-list').on('click', 'a', function(e) {
                let previous_pos = $('div#traces-list>.active').index();
                let pos = $(this).index();
                if (!$('#alert-insert').hasClass('d-none')) {
                    e.preventDefault();
                    if (pos != previous_pos) {
                        if (insert_trace(traces[previous_pos], traces[pos])) {
                            traces[pos].polyline.remove();
                            traces[pos].hmi.remove();
                            traces.splice(pos, 1);
                            update_trace(traces[previous_pos]);
                            refresh_localstorage_traces();
                        }
                    }
                    $('#alert-insert').addClass('d-none');
                }
            });

            $('#progress-message').on('click', function(e) {
                if (!$('#alert-insert').hasClass("d-none")) {
                    var trace = traces[$('div#traces-list>.active').index()]
                    if (insert_trace(trace, actualTrace)) {
                        update_trace(trace);
                        refresh_localstorage_traces();
                    }
                    $('#alert-insert').addClass("d-none");
                }
            });


            // SPLIT

            $('#split-trace').on('click', function(e) {
                $('#alert-split').removeClass("d-none");
            });

            mymap.on("click", function (e) {
                if ($('#alert-split').hasClass("d-none")) return;
                var trace = traces[$('div#traces-list>.active').index()]
                let pos_index = 0
                let pos_latlng = false
                let pos_dist = -1
                trace.polyline.getLatLngs().forEach(function(elt, index) {
                    if ((index==0) || (mymap.distance(e.latlng, elt) < pos_dist)) {
                        pos_index = index
                        pos_latlng = elt
                        pos_dist = mymap.distance(e.latlng, elt)
                    }
                })
                if (pos_dist<100) {
                    let coords = trace.route.slice(pos_index)
                    let dist = compute_distance(coords)
                    let new_trace = {name: trace.name + ' ⍆', distance: dist, route: coords}
                    gen_trace_hmi(new_trace).appendTo('#traces-list')
                    new_trace.polyline = L.polyline(new_trace.route, {color: 'green', opacity:0.8}).addTo(mymap);
                    traces.push(new_trace)

                    trace.route = trace.route.slice(0, pos_index+1)
                    trace.distance = compute_distance(trace.route)
                    update_trace(trace)
                    refresh_localstorage_traces();
                }

                $('#alert-split').addClass("d-none")
            });

            function compute_distance(route) {
                return route.slice(0, route.length-1).map((e,i) => [e, route[i+1]])
                       .map(elt => mymap.distance(elt[0], elt[1]))
                       .reduce((a,b)=>a+b, 0) / 1000.0
            }

            $('#rename-trace').on('click', function(e) {
                let name = $('div#traces-list>.active>span:first').text();
                let new_name = prompt("Nom", name);
                if (new_name != null) {
                    $('div#traces-list>.active>span:first').text(new_name);
                    traces[$('div#traces-list>.active').index()].name = new_name;
                    refresh_localstorage_traces();
                }
            });

            $('#togpx-trace').on('click', function(e) {
                let pos = $('div#traces-list>.active').index();
                let trace = traces[pos].polyline
                let name = traces[pos].name;
                let latlons = trace.getLatLngs().map(x => x.lat+","+x.lng);
                $("#download-error-toast").toast('hide')

                $.ajax({
                    type: "POST",
                    dataType: "json",
                    url: 'generate_gpx',
                    data: { name : name, points: latlons },
                    success: function ( data ) {
                        if (data.status=="OK") {
                           $("a#gpxDownload").attr("href", data.path);
                           $("a#gpxDownload")[0].click();
                        }
                        else {
                           $("#gpxMessage").text(data.message).show();
                        }
                    }
                });
            });

        }

//        $('#export-tiles').on('click', function(e) {
//            name = ""
//            $("#gpxMessage").hide();
//            $.ajax({
//                type: "GET",
//                dataType: "json",
//                url: 'generate_kml_tiles',
//                data: { name : name, tiles: selected_tiles },
//                success: function ( data ) {
//                    if (data.status=="OK") {
//                       $("a#gpxDownload").attr("href", data.path);
//                       $("a#gpxDownload")[0].click();
//                    }
//                    else {
//                       $("p#gpxMessage").text(data.message).show();
//                    }
//                }
//            });
//        });
//

    });

});