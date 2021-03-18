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

            $('input[type="text"].config-storage').each(function(){
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
            if (!('end' in markers) && selected_tiles.length==0) return;
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

        $("button#bStart").on("click", function(e) {
            selectLoc = "start";
        });
        $("button#bEnd").on("click", function(e) {
            selectLoc = "end";
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
            m = markers["end"]
            markers["end"] = markers["start"]
            markers["start"] = m
            let latlng = markers["start"].getLatLng();
            localStorage.setItem("start", latlng.lat+","+latlng.lng);
            latlng = markers["end"].getLatLng();
            localStorage.setItem("end", latlng.lat+","+latlng.lng);
            request_route();
        });

        function add_marker(name, latlng) {
            if ((name in markers) && markers[name]) {
                markers[name].setLatLng(latlng);
            } else {
                markers[name] =  L.marker(latlng, {draggable: true, title: name}).addTo(mymap).on("dragend", function(e){
                    localStorage.setItem(this.options.title, this.getLatLng().lat+","+this.getLatLng().lng);
                    request_route();
                });
            }
        }

        mymap.on("click", function (e) {
            if (selectLoc==false) return;
            add_marker(selectLoc, e.latlng);
            localStorage.setItem(selectLoc, e.latlng.lat+","+e.latlng.lng);
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
                        trace.hmi.show();
                        trace.polyline.setStyle({color:'green'})
                    } else {
                        trace.hmi.hide();
                        trace.polyline.setStyle({color:'rgba(0,0,0,0)'})
                    }
                })
            }

            function refresh_localstorage_traces() {
                localStorage.setItem("traces", JSON.stringify(traces, ['name', 'distance', 'route']))
            }

            { // ROUTES localStorage
                function gen_trace_hmi(trace) {
                    trace.hmi = $('<a href="#" class="list-group-item list-group-item-action"><span>'+trace.name+'</span><span class="badge badge-light" style="float:right;">'+trace.distance.toFixed(2)+' km</span></a>')
                    return trace.hmi
                }

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
            }

            $('#filter-activated,input#filterField').on("change", function(e) {
                filter_traces();
            })
            filter_traces();

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

            $('div#traces-list').on('click', 'a', function(e) {
                e.preventDefault();
                let previous_pos = $('div#traces-list>.active').index();
                let pos = $(this).index();
                if ($('#merge-trace').hasClass('btn-primary')) {
                    if (pos == previous_pos) {
                        //saved_traces[previous_pos].setStyle({color:'green'});
                        traces[previous_pos].polyline.setStyle({color:'green'});
                        $('div#traces-list>.active').removeClass('active');
                        $('#merge-trace').removeClass('btn-primary');
                    } else {
                        traces[previous_pos].route.push(...traces[pos].route)
                        traces[previous_pos].distance = traces[previous_pos].distance + traces[pos].distance
                        $('div#traces-list>.active>span.badge').text(traces[previous_pos].distance.toFixed(2)+" km")
                        traces[previous_pos].polyline.remove()
                        traces[pos].polyline.remove()
                        traces[previous_pos].polyline = L.polyline(traces[previous_pos].route, {color: 'blue', opacity:0.8}).addTo(mymap);
                        traces.splice(pos, 1);
                        $(this).remove();
                        refresh_localstorage_traces();
                        $('#merge-trace').removeClass('btn-primary');
                    }
                } else {
                    if (previous_pos>=0) {
                        traces[previous_pos].polyline.setStyle({color:'green'});
                        $('#trace-button-group').appendTo('#trace-menu-container')
                        $('div#traces-list>.active').removeClass('active').popover('dispose');
                    }
                    if (pos != previous_pos) {
                        $(this).addClass('active').popover({
                            html: true,
                            content:$('#trace-button-group'),
                            trigger:"manual",
                            placement: "top",
                        }).popover('show');
                        //saved_traces[pos].setStyle({color:'blue'}).bringToFront();
                        traces[pos].polyline.setStyle({color:'blue'}).bringToFront();
                    }
                }
            });

            $('#remove-trace').on('click', function(e) {
                let pos = $('div#traces-list>.active').index();
                if (pos>=0) {
                    $('#trace-button-group').appendTo('#trace-menu-container');
                    traces[pos].polyline.remove();
                    traces.splice(pos, 1);
                    $('div#traces-list>.active').remove();
                    refresh_localstorage_traces();
                }
            });

            $('#merge-trace').on('click', function(e) {
                if ($(this).hasClass('btn-primary')) {
                    $(this).removeClass('btn-primary');
                } else {
                    $(this).addClass('btn-primary');
                }
            });

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