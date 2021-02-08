$(document).ready(function(){

    $('#showMaxSquare').prop('checked', (localStorage.getItem('showMaxSquare') || "true") == "true");
    $('#showCluster').prop('checked', (localStorage.getItem('showCluster') || "true") == "true");

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


        var mymap = L.map('mapid');
        var routePolyline = false;
        var completedRoutePolyline = [];

        var tilesLayerGroup = L.layerGroup().addTo(mymap);

        function TileFromCoord(lat, lon) {
            let n = Math.pow(2,14);
            let x = Math.floor(n * (lon + 180 ) / 360);
            let lat_r = lat*Math.PI/180;
            let y = Math.floor(n * ( 1 - ( Math.log( Math.tan(lat_r) + 1/Math.cos(lat_r) ) / Math.PI ) ) / 2);
            return [x, y];
        }

        function TileIdFromLatLng(latlon) {
            let n = Math.pow(2,14);
            let x = Math.floor(n * (latlon.lng + 180 ) / 360);
            let lat_r = latlon.lat*Math.PI/180;
            let y = Math.floor(n * ( 1 - ( Math.log( Math.tan(lat_r) + 1/Math.cos(lat_r) ) / Math.PI ) ) / 2);
            return x + "_" + y;
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
            console.log("updateMapTiles()");
            console.log(selected_tiles);
            if (mymap.getZoom()<10) {
                // Remove tiles
                console.log("  ->clear tiles");
                displayed_tiles.clear();
                tilesLayerGroup.clearLayers();
            } else {
                // display tiles
                console.log("  ->display tiles");
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
                            if (visited_tiles.includes(tile_id) ^ true) {
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

        mymap.on("moveend", updateMapTiles);
        mymap.on("load", updateMapTiles);
        mymap.setView([48.85, 2.35], 10);

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
                localStorage.setItem("selected_tiles", selected_tiles);

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
        var state = false

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
                            timeoutID = false;
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

        { // MODE
            let storage_mode = localStorage.getItem('mode')
            if (storage_mode) {
                let val = $("#mode-selection").find('option[data-mode="'+storage_mode+'"]').val();
                $("#mode-selection").val(val);
            }

            $('#mode-selection').on('change', function(e) {
                e.preventDefault();
                $('#mode-selection').data('mode', $(this).find(':selected').data('mode'));
                localStorage.setItem('mode', $(this).find(':selected').data('mode'));
                request_route();
            });
        }

        {
            let turnaround_cost = localStorage.getItem('turnaround-cost')
            if (turnaround_cost) {
                let val = $("#turnaround-cost").find('option[data-cost="'+turnaround_cost+'"]').val();
                $("#turnaround-cost").val(val);
            }

            $('#turnaround-cost').change(function(){
                localStorage.setItem('turnaround-cost', $(this).find(':selected').data('cost'));
                request_route();
            });
        }

        function start_route(timeout_id) {
            if (timeout_id != active_timeout) return;
            $('button#addTrace').prop("disabled", true);
            setMessageAlert('info');
            $("#message").text($.i18n("message-state-ask-route"));
            $("#length").text("");
            $("#spinner-searching").show();
            let data = { 'sessionId'      : sessionId,
                         'start'          : latlonToQuery(markers['start'].getLatLng()),
                         'turnaroundCost':$("#turnaround-cost").find(':selected').data('cost') }
            if ('end' in markers) {
                data['end'] = latlonToQuery(markers['end'].getLatLng());
            }
            else {
                data['end'] = data['start'];
            }
            data['tiles'] = selected_tiles
            data['mode'] = $('#mode-selection').find(':selected').data('mode')

            // if (state=="complete") {
                // routePolyline.setStyle({color:'blue'});
                // completedRoutePolyline.push(routePolyline);
                // routePolyline = false
            // }

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

            if (timeoutID) {
                window.clearTimeout(timeoutID);
                timeoutID = false;
            }
            if (!('start' in markers)) return;
            if (!('end' in markers) && selected_tiles.length==0) return;
            setMessageAlert('info');
            $("#message").text($.i18n("message-state-wait"));
            $("#length").text("");

            timeoutID = window.setTimeout(start_route, 2000, ++active_timeout);
        }

        var maxSquareLayer = false;
        var clusterLayer = false;

        $( 'button#bImportStatsHunters' ).click(function ( e ) {
            var data;

            $.ajax({
                type: 'GET',
                url: 'statshunters',
                data: {url: $("#statshunters_url").val(), filter:$("#statshunters_filter").val()},
                success: function ( data ) {
                    if (data.status=="OK") {
                        if (maxSquareLayer) {
                            maxSquareLayer.remove();
                            maxSquare = false;
                        }
                        if (clusterLayer) {
                            clusterLayer.remove()
                            clusterLayer = false;
                        }
                        localStorage.setItem("statshunters_url", $("#statshunters_url").val());
                        localStorage.setItem("statshunters_filter", $("#statshunters_filter").val());
                        visited_tiles = data.tiles
                        displayed_tiles.clear();
                        tilesLayerGroup.clearLayers();
                        //mymap.fitBounds(maxSquare.getBounds().pad(0.1));
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
            e.preventDefault();
        });
        {
            let statshunters_filter = localStorage.getItem("statshunters_filter")
            if (statshunters_filter) {
                $("#statshunters_filter").val(statshunters_filter);
            }
            let statshunters_url = localStorage.getItem("statshunters_url")
            if (statshunters_url) {
                $("#statshunters_url").val(statshunters_url);
                $( 'button#bImportStatsHunters' ).click();
            }
        }
        $("#bImportStatsHuntersReset").click(function() {
            localStorage.removeItem("statshunters_filter");
            localStorage.removeItem("statshunters_url");
            if (maxSquare) {
                maxSquare.remove();
                maxSquare = false;
            }
            $("#statshunters_filter").val("");
            $("#statshunters_url").val("");
            visited_tiles = [];
            displayed_tiles.clear();
            tilesLayerGroup.clearLayers();
            updateMapTiles();
        })

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
            localStorage.setItem("selected_tiles", selected_tiles);
            updateMapTiles();
            request_route();
    });

        $("#gpxMessage").hide();

        $("button#bGenerateGpx").on("click", function(e) {
            $("#gpxMessage").hide();
            $.getJSON({
                url: 'generate_gpx',
                data: { 'sessionId': sessionId, name : $("input#gpxFilename").val() },
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
            let bounds = false;
            function load_marker(name) {
                let lcs = localStorage.getItem(name)
                if (lcs) {
                    add_marker(name, lcs.split(','));
                    if (bounds) {
                        bounds.extend(markers[name].getLatLng().toBounds(1000));
                    }
                    else {
                        bounds = markers[name].getLatLng().toBounds(1000);
                    }
                }
            }
            load_marker("start");
            load_marker("end");
            selected_tiles = []
            let lcs = localStorage.getItem("selected_tiles")
            console.log(lcs)
            if (lcs) {
                selected_tiles = lcs.split(",")
                for (let i=0; i<selected_tiles.length; i++) {
                    if (bounds) {
                        bounds.extend(boundsFromTileId(selected_tiles[i]));
                    }
                    else {
                        bounds = boundsFromTileId(selected_tiles[i]);
                    }

                }
                updateMapTiles();
            }
            mymap.fitBounds(bounds);
            request_route();
        }

        {
            var saved_traces =[];

            { // ROUTES localstorage
                let trace_count = parseInt(localStorage.getItem("trace_count") || "0");
                for (let trace_val=0; trace_val<trace_count; trace_val++) {
                    let coords = localStorage.getItem('trace'+trace_val+'_coords').split(",").map(x => x.split(" "));
                    let rp = L.polyline(coords, {color: 'aqua', opacity:0.8}).addTo(mymap);
                    saved_traces.push(rp);
                    let name = localStorage.getItem('trace'+trace_val+'_name');
                    let dist = localStorage.getItem('trace'+trace_val+'_length');
                    $('<a href="#" class="list-group-item list-group-item-action"><span>'+name+'</span><span class="badge badge-light" style="float:right;">'+dist+'</span></a>').appendTo('#traces-list')
                }
            }

            function refresh_localstorage_traces() {
                count = $('div#traces-list').length;
                localStorage.setItem("trace_count", 0);
                $('div#traces-list').children().each(function(index){
                    console.log(index)
                    localStorage.setItem('trace'+index+'_name', $(this).find('span:first').text());
                    localStorage.setItem('trace'+index+'_length', $(this).find('span.badge').text());
                    localStorage.setItem('trace'+index+'_coords', saved_traces[index].getLatLngs().map(x => x.lat+" "+x.lng));
                    localStorage.setItem("trace_count", index+1);
                });
            }

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
                saved_traces.push(routePolyline.setStyle({color:'aqua'}));
                routePolyline = false;
                let name = $('#traceName').val();
                let dist = $("#length").text();
                $('<a href="#" class="list-group-item list-group-item-action"><span>'+name+'</span><span class="badge badge-light" style="float:right;">'+dist+'</span></a>').appendTo('#traces-list')
                $('button#addTrace').prop("disabled", true);
                refresh_localstorage_traces();
            });

            $('button#addTrace').prop("disabled", true);

            $('div#traces-list').on('click', 'a', function(e) {
                e.preventDefault();
                let previous_pos = $('div#traces-list>.active').index();
                let pos = $(this).index();
                if ($('#merge-trace').hasClass('btn-primary')) {
                    if (pos == previous_pos) {
                        saved_traces[previous_pos].setStyle({color:'aqua'});
                        $('div#traces-list>.active').removeClass('active');
                        $('#merge-trace').removeClass('btn-primary');
                        $('#trace-button-group').hide();
                    } else {
                        let a = saved_traces[previous_pos]
                        let b = saved_traces[pos]
                        for (const latlng of b.getLatLngs()) {
                            a.addLatLng(latlng);
                        }
                        $('div#traces-list>.active>span.badge').text((parseFloat($('div#traces-list>.active>span.badge').text()) + parseFloat($(this).find("span.badge").text())).toFixed(2)+" km")
                        saved_traces[pos].remove();
                        saved_traces.splice(pos, 1);
                        $(this).remove();
                        refresh_localstorage_traces();
                        $('#merge-trace').removeClass('btn-primary');
                    }
                } else {
                    if (previous_pos>=0) {
                        saved_traces[previous_pos].setStyle({color:'aqua'});
                        $('div#traces-list>.active').removeClass('active');
                    }
                    if (pos != previous_pos) {
                        $(this).addClass('active');
                        saved_traces[pos].setStyle({color:'blue'}).bringToFront();
                        $('#trace-button-group').show();
                    } else {
                        $('#trace-button-group').hide();
                    }
                }
            });
            $('#trace-button-group').hide();

            $('#remove-trace').on('click', function(e) {
                let pos = $('div#traces-list>.active').index();
                if (pos>=0) {
                    saved_traces[pos].remove();
                    saved_traces.splice(pos, 1);
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
                    refresh_localstorage_traces();
                }
            });

            $('#togpx-trace').on('click', function(e) {
                let pos = $('div#traces-list>.active').index();
                let name = $('div#traces-list>.active>span:first').text();
                let trace = saved_traces[pos]
                console.log("togpx-trace.click()")
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

        $('#export-tiles').on('click', function(e) {
            name = ""
            $("#gpxMessage").hide();
            $.ajax({
                type: "GET",
                dataType: "json",
                url: 'generate_kml_tiles',
                data: { name : name, tiles: selected_tiles },
                success: function ( data ) {
                    if (data.status=="OK") {
                       $("a#gpxDownload").attr("href", data.path);
                       $("a#gpxDownload")[0].click();
                    }
                    else {
                       $("p#gpxMessage").text(data.message).show();
                    }
                }
            });
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
            localStorage.setItem('showCluster', this.checked);
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
            localStorage.setItem('showMaxSquare', this.checked);
        });


    });

});