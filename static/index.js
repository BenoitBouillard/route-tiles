$(document).ready(function(){
    $.i18n(/*{locale:'en'}*/).load({
        'en': 'i18n/en.json',
        'fr': 'i18n/fr.json'
    }).done( function(){
        if (localStorage.getItem('locale')) {
            $.i18n().locale = localStorage.getItem('locale');
        }
        $('.switch-locale').on('click', 'a', function(e){
            e.preventDefault();
            localStorage.setItem('locale', $(this).data('locale'));
            $.i18n().locale = $(this).data('locale');
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
        var missing_tiles = []
        var visited_tiles = []
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
                            if (missing_tiles.includes(tile_id)) {
                                color = 'red';
                                weight = 1.0;
                            }
                            if (visited_tiles.includes(tile_id)) {
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

        function route_status(timeout_id) {
            if (timeout_id != active_timeout) return;
            $.getJSON({
                url: 'route_status',
                data: { 'sessionId': sessionId, 'findRouteId' : routeId },
                success: function ( data ) {
                    state = data['state']
                    $("p#message").text($.i18n("message-state-"+data['state']));
                    if ('route' in data) {
                        routeId = data['findRouteId']
                        if (!routePolyline) {
                            routePolyline = L.polyline(data.route, {color: '#FF0000', opacity:0.8}).addTo(mymap);
                        } else {
                            routePolyline.setLatLngs(data.route).bringToFront();
                        }
                        $("p#length").text(parseFloat(data['length']).toFixed(2)+" km");
                    }
                    if (data['state']!='complete') {
                        timeoutID = window.setTimeout(route_status, 1000, ++active_timeout);
                    } else {
                        timeoutID = false;
                        $('button#addTrace').prop("disabled", false);
                    }
                }
            });
        };

        { // MODE
            $('a.dropdown-item').on('click', function(e) {
                if ($(this).data('mode') != $('#mode-selection').data('mode')) {
                    $('#mode-selection').data('mode', $(this).data('mode'));
                    $('#mode-selection').data('i18n', 'message-mode-'+$(this).data('mode'));
                    $('#mode-selection').i18n();
                    localStorage.setItem('mode', $(this).data('mode'));
                    request_route();
                }
            });
            let lmd = localStorage.getItem('mode')
            if (lmd) {
                $('#mode-selection').data('mode', lmd);
                $('#mode-selection').data('i18n', 'message-mode-'+lmd);
                $('#mode-selection').attr('data-i18n', 'message-mode-'+lmd); // without this i18n don't work ! Why ?
                $('#mode-selection').i18n();
            }
        }


        function start_route(timeout_id) {
            if (timeout_id != active_timeout) return;
            $('button#addTrace').prop("disabled", true);
            $("p#message").text($.i18n("message-state-ask-route"));
            let data = { 'sessionId': sessionId, start : latlonToQuery(markers['start'].getLatLng()) }
            if ('end' in markers) {
                data['end'] = latlonToQuery(markers['end'].getLatLng());
            }
            else {
                data['end'] = data['start'];
            }
            data['tiles'] = selected_tiles
            data['mode'] = $('#mode-selection').data('mode')

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
                    }
                    else {
                        $("p#message").text($.i18n("message-state-fail")+":"+data['message']);
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
            $("p#message").text($.i18n("message-state-wait"));

            timeoutID = window.setTimeout(start_route, 2000, ++active_timeout);
        }



        var maxSquare = false;


        $('form#set_kml input').on('change', function(e) {
            if ($('form#set_kml input').val()) {
                $( 'form#set_kml' ).submit();
            }
        });
        $( 'form#set_kml' ).submit(function ( e ) {
            var data;

            data = new FormData();
            data.append( 'file', $( '#file' )[0].files[0] );

            $.ajax({
                type: 'POST',
                url: 'set_kml',
                data: data,
                processData: false,
                contentType:false,
                success: function ( data ) {
                    let tiles = data.tiles;
                    if (data.status=="OK") {
                        if (maxSquare) {
                            maxSquare.remove();
                            maxSquare = false;
                        }
                        missing_tiles = data.tiles
                        maxSquare = L.rectangle(data.maxSquare, {interactive:false, color: 'red', fillOpacity:0, weight:2.0}).addTo(mymap);
                        displayed_tiles.clear();
                        tilesLayerGroup.clearLayers();
                        mymap.fitBounds(maxSquare.getBounds().pad(0.1));
                    }
                    else {
                        alert(data.message);
                    }
                }
            });

            e.preventDefault();
        });

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

        $("button#bGenerateGpx").on("click", function(e) {
            $.getJSON({
                url: 'generate_gpx',
                data: { 'sessionId': sessionId, name : $("input#gpxFilename").val() },
                success: function ( data ) {
                    if (data.status!="OK") {
                        $("p#gpxMessage").text(data.message);
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

        mymap.on("click", function (e) {
            if (selectLoc==false) return;
            if ((selectLoc in markers) && markers[selectLoc]) {
                markers[selectLoc].setLatLng(e.latlng);
            } else {
                markers[selectLoc] = L.marker(e.latlng).addTo(mymap);
            }
            localStorage.setItem(selectLoc, e.latlng.lat+","+e.latlng.lng);
           selectLoc = false;

            request_route();
        });

        { // local Storage recovery
            let bounds = false;
            function addMarker(name) {
                let lcs = localStorage.getItem(name)
                if (lcs) {
                    markers[name] = L.marker(lcs.split(',')).addTo(mymap);
                    if (bounds) {
                        bounds.extend(markers[name].getLatLng().toBounds(1000));
                    }
                    else {
                        bounds = markers[name].getLatLng().toBounds(1000);
                    }
                }
            }
            addMarker("start");
            addMarker("end");
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
                        if (! visited_tiles.includes(tile_id)) {
                            visited_tiles.push(tile_id);
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
                let dist = $("p#length").text();
                $('<a href="#" class="list-group-item list-group-item-action"><span>'+name+'</span><span class="badge badge-light" style="float:right;">'+dist+'</span></a>').appendTo('#traces-list')
                $('button#addTrace').prop("disabled", true);
                refresh_localstorage_traces();
            });

            $('button#addTrace').prop("disabled", true);

            $('div#traces-list').on('click', 'a', function(e) {
                let previous_pos = $('div#traces-list>.active').index();
                let pos = $(this).index();
                if ($('#merge-trace').hasClass('btn-primary')) {
                    if (pos == previous_pos) {
                        saved_traces[previous_pos].setStyle({color:'aqua'});
                        $('div#traces-list>.active').removeClass('active');
                        $('#merge-trace').removeClass('btn-primary');
                        $('#trace-button-group>button').prop("disabled", true);
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
                    }
                } else {
                    if (previous_pos>=0) {
                        saved_traces[previous_pos].setStyle({color:'aqua'});
                        $('div#traces-list>.active').removeClass('active');
                    }
                    if (pos != previous_pos) {
                        $(this).addClass('active');
                        saved_traces[pos].setStyle({color:'blue'}).bringToFront();
                        $('#trace-button-group>button').prop("disabled", false);
                    } else {
                        $('#trace-button-group>button').prop("disabled", true);
                    }
                }
            });
            $('#trace-button-group>button').prop("disabled", true);

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
                           $("p#gpxMessage").text(data.message);
                        }
                    }
                });
            });

        }

        $('#export-tiles').on('click', function(e) {
            name = ""
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
                       $("p#gpxMessage").text(data.message);
                    }
                }
            });
        });


    });

});