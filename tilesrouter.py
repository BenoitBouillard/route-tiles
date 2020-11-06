#!/usr/bin/python
# -*- coding: utf-8 -*-

import threading
from pathlib import Path

import gpxpy
import gpxpy.gpx
from fastkml import kml, styles
from shapely.geometry import Point, Polygon

from pyroutelib3 import Datastore
from tile import Tile, CoordDict, coord_from_tile
from utils import *


def latlons_to_gpx(latlons, filename, name):
    gpx = gpxpy.gpx.GPX()

    # Create first track in our GPX:
    gpx_track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(gpx_track)

    # Create first segment in our GPX track:
    gpx_segment = gpxpy.gpx.GPXTrackSegment()
    gpx_track.segments.append(gpx_segment)

    # Create points:
    for coord in latlons:
        gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(coord[0], coord[1]))

    with open(filename, 'w') as hf:
        hf.write(gpx.to_xml())
    return True


def tiles_to_kml(tiles, filename, name):
    # Create the root KML object
    k = kml.KML()
    ns = '{http://www.opengis.net/kml/2.2}'

    s = styles.Style(id="s", styles=[styles.LineStyle(color="ff0000ff", width=1)])

    # Create a KML Document and add it to the KML root object
    d = kml.Document(ns, name=name, styles=[s])
    k.append(d)

    # Create a KML Folder and add it to the Document
    f = kml.Folder(ns, name=name)
    d.append(f)

    # Create a Placemark with a simple polygon geometry and add it to the
    # second folder of the Document
    for tile_id in tiles:
        tile = Tile(tile_id)
        p = kml.Placemark(ns, tile_id, styleUrl="#s")
        p.geometry = tile.line_string_lon_lat
        f.append(p)

    print(k.to_string(prettyprint=True))
    with open(filename, 'w') as hf:
        hf.write(k.to_string(prettyprint=True))
    return True


class Route(object):
    def __init__(self, route, router):
        self.route = route
        self.routeLatLons = list(map(router.node_lat_lon, route))
        self.compute_length(self.routeLatLons)
        self.length = self.compute_length(self.routeLatLons)

    @staticmethod
    def compute_length(route_latlons):
        length = 0
        previous = route_latlons[0]
        for latlon in route_latlons[1:]:
            length += distance(previous, latlon)
            previous = latlon
        return length

    def to_gpx(self, filename, name):
        return latlons_to_gpx(self.routeLatLons, filename, name)


def debug_export_tiles(tiles):
    with open('debug/tiles.js', 'w') as hf:
        hf.write("var tiles = [\n")
        for t in tiles:
            hf.write(" [ \n")
            for lat, lon in t.edges:
                hf.write("[{},{}],\n".format(lat, lon))
            hf.write("  ],\n")
        hf.write("];\n")
        hf.write("var nodes = [\n")
        for t in tiles:
            for e in t.entryNodeId:
                hf.write("[{},{}],\n".format(*e.latlon))
        hf.write("];\n")

ERR_NO = 0
ERR_NO_TILE_ENTRY_POINT = 1
ERR_ABORT_REQUEST = 2
ERR_ROUTE_ERROR = 1000

def compute_missing_kml(file):
    k = kml.KML()
    doc = file.read()
    try:
        k.from_string(doc)
    except Exception as e:
        print(e)
        return False

    features = list(k.features())
    folder = list(features[0].features())[0]
    # folder = features[0]
    xmin, xmax, ymin, ymax = None, None, None, None
    not_found_tiles = []
    for placemark in folder.features():
        tile = Tile(placemark.geometry.coords)
        not_found_tiles.append(tile.uid)
        if not xmin or tile.x < xmin:
            xmin = tile.x
        if not xmax or tile.x > xmax:
            xmax = tile.x
        if not ymin or tile.y < ymin:
            ymin = tile.y
        if not ymax or tile.y > ymax:
            ymax = tile.y

    max_square = 1
    max_square_x = 0
    max_square_y = 0

    def is_square(pos_x, pos_y, m):
        if pos_x + m > xmax or pos_y + m > ymax:
            return False
        for dx in range(m):
            for dy in range(m):
                uid = "{}_{}".format(pos_x + dx, pos_y + dy)
                if uid in not_found_tiles:
                    return False
        return True

    # Trouver le carré le plus grand
    for x in range(xmin, xmax + 1):
        for y in range(ymin, ymax + 1):
            while True:
                if is_square(x, y, max_square + 1):
                    max_square_x = x
                    max_square_y = y
                    max_square = max_square + 1
                else:
                    break  # while break

    max_square_coord = (coord_from_tile(max_square_x, max_square_y),
                        coord_from_tile(max_square_x + max_square, max_square_y + max_square))
    print("Max square:{} at {},{}".format(max_square, max_square_x, max_square_y))
    return {"tiles": not_found_tiles, "max": max_square, "coord": max_square_coord}


class RouteServer(object):
    def __init__(self):
        self.stored_tiles = {}
        self.router = None
        self._exit = False

        self.mode = None
        self.thread = None

        self._complete = False
        self.error_code = ERR_NO
        self.error_args = ""
        self._min_route = None
        self.min_length = None
        self.progress = 0

        # Parameter for background task
        self.run_data = {}

    def start_route(self, mode, start_loc, end_loc, tiles, config={}, thread=True):
        print(tiles)

        if self.thread and not self.is_complete:
            print("Abord previous route...")
            self.abort()
            self.thread.join()
            print("   ...OK")
        if mode != self.mode:
            self.mode = mode
            self.stored_tiles = {}
            self.router = Datastore(mode, cache_dir=str(Path.home().joinpath('.tilescache')))

        self._exit = False

        self._min_route = None
        self.min_length = None
        self.error_code = ERR_NO
        self.error_args = ""
        self._complete = False
        self.progress = 100.0
        self.run_data = {
            'start' : start_loc,
            'end'   : end_loc,
            'tiles' : tiles,
            'config': config
        }

        if thread:
            self.thread = threading.Thread(target=self.run)
            # Background thread will finish with the main program
            self.thread.setDaemon(True)
            # Start YourLedRoutine() in a separate thread
            self.thread.start()

        else:
            self.run()

        return self.is_complete, self.route

    @property
    def route(self):
        return self.min_route

    def abort(self):
        self._exit = True

    @property
    def is_complete(self):
        return self._complete

    def run(self):
        coord_dict = CoordDict(self.router)
        start_point = coord_dict.get(*self.run_data['start'])
        end_point = coord_dict.get(*self.run_data['end'])

        selected_tiles = []
        for t in self.run_data['tiles']:
            if self._exit:
                self.error_code = ERR_ABORT_REQUEST
                return False

            if t not in self.stored_tiles:
                self.stored_tiles[t] = Tile(t)
            tile = self.stored_tiles[t]
            if Polygon(tile.linear_ring()).contains(Point(start_point.latlon)) or \
                    Polygon(tile.linear_ring()).contains(Point(end_point.latlon)):
                # Tile contains start or end. No need to test
                continue
            tile.get_entry_points(self.router)
            selected_tiles.append(tile)
            if not self.stored_tiles[t].entryNodeId:
                self.error_code = ERR_NO_TILE_ENTRY_POINT
                self.error_args = [t]
                self._complete = True
                return False

        debug_export_tiles(selected_tiles)
        if self.run_data['config']['route_mode']=="isochrone-dist":
            status, r = self.do_route_isochrone(start_point.nodeId, self.run_data['config'])
        else:
            status, r = self.do_route_with_crossing_zone(start_point.nodeId, end_point.nodeId,
                                                         frozenset(selected_tiles), self.run_data['config'])
        if status != "success":
            self.error_code = ERR_ROUTE_ERROR
            self.error_args = ""
            route = None
        else:
            route = Route(r, router=self.router)
            print("length:", route.length)

            self.min_length = route.length
            self._min_route = route
            print("\n**** FIND MIN ROUTE {:.2f}km ****\n".format(self.min_length))

        self.progress = 100.0
        print_progress_bar(100, 100)
        self._complete = True
        return route

    @property
    def min_route(self):
        if self._min_route is None:
            return None
        if isinstance(self._min_route, str):
            self._min_route = Route([int(i) for i in self._min_route.split(",")], router=self.router)
        return self._min_route

    def explore_routes_tile_exit(self, start, tile, mandatoryNodes):
        """Do the routing"""
        _closed = set()
        _queue = []
        _closeNode = True

        if start in tile.routesEntryNodes:
            return tile.routesEntryNodes[start]

        tile_bounds = Polygon(tile.linear_ring(offset=9.9))

        find_routes = []

        def _export_queue(new_item=None):
            nonlocal _closed, _queue, _closeNode
            with open('debug/routes.js', 'w') as hf:
                hf.write("var routes = [\n")
                if new_item:
                    route = [int(i) for i in new_item["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0:.3f}',\n".format(new_item['cost']))
                    hf.write("  'length':{},\n".format(new_item['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                for q in _queue+find_routes:
                    route = [int(i) for i in q["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0:.3f}',\n".format(q['cost']))
                    hf.write("  'length':{},\n".format(q['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                hf.write("];\n")

        def _queue_insert(queue_item):
            nonlocal _queue
            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["cost"] > queue_item["cost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

        # Define function that addes to the queue
        def _add_to_queue(item_start, item_end, queue_so_far, item_weight=1):
            """Add another potential route to the queue"""
            nonlocal _closed, _queue, _closeNode

            # Assume start and end nodes have positions
            if item_end not in self.router.rnodes or item_start not in self.router.rnodes:
                return

            # Get data around end node
            self.router.get_area(self.router.rnodes[item_end][0], self.router.rnodes[item_end][1])

            # Ignore if route is not traversible
            if item_weight == 0:
                return

            # Do not turn around at a node (don't do this: a-b-a)
            # if len(queueSoFar["nodes"].split(",")) >= 2 and queueSoFar["nodes"].split(",")[-2] == str(end):
            #    return

            edge_cost = distance(self.router.rnodes[item_start], self.router.rnodes[item_end]) / item_weight

            total_cost = queue_so_far["cost"] + edge_cost

            all_nodes = queue_so_far["nodes"] + "," + str(item_end)

            # Check if path queueSoFar+end is not forbidden
            for i in self.router.forbiddenMoves:
                if i in all_nodes:
                    _closeNode = False
                    return

            # Check if we have a way to 'end' node
            end_queue_item = None
            for i in _queue:
                if i["end"] == item_end:
                    end_queue_item = i
                    break

            if end_queue_item :
                # If we do, and known total_cost to end is lower we can ignore the queueSoFar path
                if end_queue_item["cost"] < total_cost:
                    return
                # If the queued way to end has higher total cost, remove it
                # (and add the queueSoFar scenario, as it's cheaper)
                elif end_queue_item:
                    _queue.remove(end_queue_item)

            # Check against mandatory turns
            force_next_nodes = None
            if queue_so_far.get("mandatoryNodes", None):
                force_next_nodes = queue_so_far["mandatoryNodes"]

            else:
                for activationNodes, nextNodes in self.router.mandatoryMoves.items():
                    if all_nodes.endswith(activationNodes):
                        _closeNode = False
                        force_next_nodes = nextNodes.copy()
                        break

            # Create a hash for all the route's attributes
            queue_item = {
                "cost": total_cost,
                "nodes": all_nodes,
                "end": item_end,
                "mandatoryNodes": force_next_nodes
            }
            _queue_insert(queue_item)

        queue_item = {
            "cost": 0,
            "nodes": str(start),
            "end": start,
            "mandatoryNodes": mandatoryNodes
        }
        _queue_insert(queue_item)

        while _queue:
            _closeNode = True
            # _export_queue()

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            next_item = _queue.pop(0)

            considered_node = next_item["end"]

            # If we already visited the node, ignore it
            if considered_node in _closed:
                continue

            # exit the zone - success
            if not tile_bounds.contains(Point(*self.router.node_lat_lon(considered_node))):
                find_routes.append(next_item)
                continue

            # Check if we preform a mandatory turn
            if next_item["mandatoryNodes"]:
                _closeNode = False
                next_node = next_item["mandatoryNodes"].pop(0)
                if considered_node in self.router.routing and \
                        next_node in self.router.routing.get(considered_node, {}).keys():
                    _add_to_queue(considered_node, next_node, next_item,
                                  self.router.routing[considered_node][next_node])

            # If no, add all possible nodes from x to queue
            elif considered_node in self.router.routing:
                for next_node, weight in list(self.router.routing[considered_node].items()):
                    if next_node not in _closed:
                        _add_to_queue(considered_node, next_node, next_item, weight)

            if _closeNode:
                _closed.add(considered_node)

        #_export_queue()
        tile.routesEntryNodes[start] = find_routes
        return find_routes

    def do_route_with_crossing_zone(self, start, end, zones, config):
        """Do the routing"""
        _closed = {(start, frozenset(zones))}
        _queue = []
        _closeNode = True
        _end = end
        min_dists = {}
        min_dists_fast = {}

        def _export_queue(new_item=None):
            nonlocal _closed, _queue, _closeNode
            with open('debug/routes.js', 'w') as hf:
                hf.write("var routes = [\n")
                if new_item:
                    route = [int(i) for i in new_item["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0}-{1:.3f}',\n".format(len(new_item['not_visited_zones']),
                                                                new_item['heuristic_cost']))
                    hf.write("  'length':{},\n".format(new_item['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                for q in _queue:
                    route = [int(i) for i in q["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0}-{1:.3f}',\n".format(len(q['not_visited_zones']), q['heuristic_cost']))
                    hf.write("  'length':{},\n".format(q['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.node_lat_lon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                hf.write("];\n")

        def _queue_insert(queue_item):
            nonlocal _queue
            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["heuristic_cost"] > queue_item["heuristic_cost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

        # Define function that addes to the queue
        def _add_to_queue(item_start, item_not_visited_zones, item_end, queue_so_far, item_weight=1):
            """Add another potential route to the queue"""
            nonlocal _closed, _queue, _closeNode, min_dists, min_dists_fast

            # Assume start and end nodes have positions
            if item_end not in self.router.rnodes or item_start not in self.router.rnodes:
                return

            # Get data around end node
            self.router.get_area(self.router.rnodes[item_end][0], self.router.rnodes[item_end][1])

            # Ignore if route is not traversible
            if item_weight == 0:
                return

            # Do not turn around at a node (don't do this: a-b-a)
            # if len(queueSoFar["nodes"].split(",")) >= 2 and queueSoFar["nodes"].split(",")[-2] == str(end):
            #    return

            edge_cost = distance(self.router.rnodes[item_start], self.router.rnodes[item_end]) / item_weight

            # if turn around add additional cost
            if config.get('turnaround_cost', 0)>0:
                queue_so_far_nodes = queue_so_far["nodes"].split(',')
                if len(queue_so_far_nodes)>2:
                    if str(item_end) == queue_so_far_nodes[-2]:
                        #_export_queue(queue_so_far)
                        #print("Turnaround cost")
                        edge_cost += config['turnaround_cost']

            total_cost = queue_so_far["cost"] + edge_cost

            def _min_dist(start_loc, tiles, end_loc, store=True, fast=False):
                nonlocal min_dists, min_dists_fast
                if self._exit:
                    return 0
                md = min_dists_fast if fast else min_dists
                # compute flyby min distance by visiting all tiles
                if len(tiles) == 0:
                    return distance(start_loc, end_loc)

                if (start_loc, frozenset(tiles), end_loc) in md:
                    return md[(start_loc, frozenset(tiles), end_loc)]

                min_dist = None
                for t in tiles:
                    remain_tiles = set(tiles) - {t}
                    if fast and len(t.entryNodeId) > 4:
                        ep = t.edges
                    else:
                        ep = [n.latlon for n in t.entryNodeId]
                    for entry in ep:
                        pa = distance(start_loc, entry)
                        pb = _min_dist(entry, remain_tiles, end_loc, fast=fast)
                        if min_dist is None or pa + pb < min_dist:
                            min_dist = pa + pb
                if store:
                    md[(start_loc, frozenset(tiles), end_loc)] = min_dist
                return min_dist

            # t = time.time() if len(min_dists)==0 else None
            hc = _min_dist(self.router.rnodes[item_end], item_not_visited_zones, self.router.rnodes[_end], False,
                           len(item_not_visited_zones) > 5)
            # if t:
            # print("min dist time:{}".format(time.time()-t))
            heuristic_cost = total_cost + hc

            all_nodes = queue_so_far["nodes"] + "," + str(item_end)

            # Check if path queueSoFar+end is not forbidden
            for i in self.router.forbiddenMoves:
                if i in all_nodes:
                    _closeNode = False
                    return

            # Check if we have a way to 'end' node
            end_queue_item = None
            for i in _queue:
                if (i["end"], i["not_visited_zones"]) == (item_end, item_not_visited_zones):
                    end_queue_item = i
                    break

            if end_queue_item :
                # If we do, and known total_cost to end is lower we can ignore the queueSoFar path
                if end_queue_item["cost"] < total_cost:
                    return
                # If the queued way to end has higher total cost, remove it
                # (and add the queueSoFar scenario, as it's cheaper)
                elif end_queue_item:
                    _queue.remove(end_queue_item)

            # Check against mandatory turns
            force_next_nodes = None
            if queue_so_far.get("mandatoryNodes", None):
                force_next_nodes = queue_so_far["mandatoryNodes"]

            else:
                for activationNodes, nextNodes in self.router.mandatoryMoves.items():
                    if all_nodes.endswith(activationNodes):
                        _closeNode = False
                        force_next_nodes = nextNodes.copy()
                        break

            # Create a hash for all the route's attributes
            queue_item = {
                "cost": total_cost,
                "heuristic_cost": heuristic_cost,
                "nodes": all_nodes,
                "end": item_end,
                "not_visited_zones": item_not_visited_zones,
                "mandatoryNodes": force_next_nodes
            }

            _queue_insert(queue_item)



        # Start by queueing all outbound links from the start node
        if start not in self.router.routing:
            raise KeyError("node {} doesn't exist in the graph".format(start))

        elif start == end and not zones:
            return "no_route", []

        else:
            not_visited_zones = frozenset(zones)
            for linkedNode in list(self.router.routing[start]):
                weight = self.router.routing[start][linkedNode]
                _add_to_queue(start, not_visited_zones, linkedNode, {"cost": 0, "nodes": str(start)}, weight)

        # Limit for how long it will search
        count = 0
        while count < 1000000 and not self._exit:
            count += 1
            _closeNode = True
            #_export_queue()

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            if len(_queue) > 0:
                next_item = _queue.pop(0)
            else:
                return "no_route", []

            considered_node = next_item["end"]
            not_visited_zones = next_item["not_visited_zones"]

            if not self.min_length or next_item['cost'] > self.min_length:
                self.min_length = next_item['cost']
                self._min_route = next_item['nodes']
                self.progress = 100.0 * next_item['cost'] / next_item['heuristic_cost']
                print_progress_bar(next_item['cost'], next_item['heuristic_cost'])

            is_enter_new_tile = False
            for zone in not_visited_zones:
                if considered_node in zone.entry_nodes_id:
                    # Enter in a new zone
                    not_visited_zones = not_visited_zones - {zone}
                    if config.get('turnaround_cost', 0)>0:
                        is_enter_new_tile = True
                        routes_across_tile = self.explore_routes_tile_exit(considered_node, zone, next_item['mandatoryNodes'])
                        for route in routes_across_tile:
                            first_nodes = next_item['nodes'].split(',')[:-1]
                            add_cost = 0
                            if first_nodes[-1] in route['nodes'].split(','):
                                add_cost += config.get('turnaround_cost', 0)


                            queue_item = {
                                "cost": next_item['cost'] + route['cost'] + add_cost,
                                "heuristic_cost": next_item['heuristic_cost'] + route['cost'] + add_cost,
                                "nodes": next_item['nodes'] + ',' + route['nodes'],
                                "end": route['end'],
                                "not_visited_zones": not_visited_zones,
                                "mandatoryNodes": route['mandatoryNodes']
                            }
                            _queue_insert(queue_item)
                            _closed.add((int(route['nodes'].split(',')[-2]), not_visited_zones))
            if is_enter_new_tile:
                _closed.add((considered_node, not_visited_zones))
                #_export_queue()
                continue

            # If we already visited the node, ignore it
            if (considered_node, not_visited_zones) in _closed:
                continue

            # Found the end node - success
            if considered_node == end:
                if len(not_visited_zones) == 0:
                    _export_queue(next_item)
                    print(next_item)
                    return "success", [int(i) for i in next_item["nodes"].split(",")]

            # Check if we preform a mandatory turn
            if next_item["mandatoryNodes"]:
                _closeNode = False
                next_node = next_item["mandatoryNodes"].pop(0)
                if considered_node in self.router.routing and \
                        next_node in self.router.routing.get(considered_node, {}).keys():
                    _add_to_queue(considered_node, not_visited_zones, next_node, next_item,
                                  self.router.routing[considered_node][next_node])

            # If no, add all possible nodes from x to queue
            elif considered_node in self.router.routing:
                for next_node, weight in list(self.router.routing[considered_node].items()):
                    if (next_node, not_visited_zones) not in _closed:
                        _add_to_queue(considered_node, not_visited_zones, next_node, next_item, weight)

            if _closeNode:
                _closed.add((considered_node, not_visited_zones))

        else:
            return "gave_up", []

    def if_route_exists(self, start, end, forbidden_nodes):
        """Do the routing"""
        _closed = {start}
        _queue = []
        _closeNode = True
        _end = end

        def _queue_insert(queue_item):
            nonlocal _queue
            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["heuristic_cost"] > queue_item["heuristic_cost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

        # Define function that addes to the queue
        def _add_to_queue(item_start, item_end, queue_so_far):
            """Add another potential route to the queue"""
            nonlocal _closed, _queue, _closeNode, end

            # Do not turn around at a node (don't do this: a-b-a)
            # if len(queueSoFar["nodes"].split(",")) >= 2 and queueSoFar["nodes"].split(",")[-2] == str(end):
            #    return

            edge_cost = distance(self.router.rnodes[item_start], self.router.rnodes[item_end])

            total_cost = queue_so_far["cost"] + edge_cost

            # t = time.time() if len(min_dists)==0 else None
            hc = distance(self.router.rnodes[item_end], self.router.rnodes[end])

            heuristic_cost = total_cost + hc

            all_nodes = queue_so_far["nodes"] + "," + str(item_end)


            # Check if we have a way to 'end' node
            end_queue_item = None
            for i in _queue:
                if i["end"] == item_end:
                    end_queue_item = i
                    break

            if end_queue_item :
                # If we do, and known total_cost to end is lower we can ignore the queueSoFar path
                if end_queue_item["cost"] < total_cost:
                    return
                # If the queued way to end has higher total cost, remove it
                # (and add the queueSoFar scenario, as it's cheaper)
                elif end_queue_item:
                    _queue.remove(end_queue_item)

            # Create a hash for all the route's attributes
            queue_item = {
                "cost": total_cost,
                "heuristic_cost": heuristic_cost,
                "nodes": all_nodes,
                "end": item_end
            }

            _queue_insert(queue_item)



        # Start by queueing all outbound links from the start node
        if start not in self.router.routing:
            raise KeyError("node {} doesn't exist in the graph".format(start))

        elif start == end:
            return True
        else:
            for linkedNode in list(self.router.routing[start]):
                _add_to_queue(start, linkedNode, {"cost": 0, "nodes": str(start)})

        # Limit for how long it will search
        count = 0
        while count < 1000000 and not self._exit:
            count += 1
            _closeNode = True
            #_export_queue()

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            if len(_queue) > 0:
                next_item = _queue.pop(0)
            else:
                return False

            considered_node = next_item["end"]

            # If we already visited the node, ignore it
            if considered_node in _closed:
                continue

            # Found the end node - success
            if considered_node == end:
                return True


            # If no, add all possible nodes from x to queue
            elif considered_node in self.router.routing:
                for next_node, weight in list(self.router.routing[considered_node].items()):
                    if next_node not in _closed and next_node not in forbidden_nodes:
                        _add_to_queue(considered_node, next_node, next_item)

            if _closeNode:
                _closed.add(considered_node)
        else:
            return False

    def do_route_isochrone(self, start, config):
        """Do the routing"""
        _queue = []
        _closeNode = True
        _longest_route = None

        def _export_queue(new_item=None):
            nonlocal _queue, _closeNode
            try:
                with open('debug/routes.js', 'w') as hf:
                    hf.write("var routes = [\n")
                    if new_item:
                        route = [i for i in new_item['right']['nodes'][::-1]+new_item['left']["nodes"]]
                        hf.write(" { \n")
                        hf.write("  'name':'{0}-{1:.3f}',\n".format('x',
                                                                    new_item['cost']))
                        hf.write("  'length':{},\n".format(new_item['cost']))
                        hf.write("  'route':[\n")
                        for lat, lon in list(map(self.router.node_lat_lon, route)):
                            hf.write("[{},{}],\n".format(lat, lon))
                        hf.write("  ],\n")
                        hf.write("  },\n")
                    for q in _queue[:100]:
                        route = [i for i in q['right']['nodes'][::-1]+q['left']["nodes"]]
                        hf.write(" { \n")
                        hf.write("  'name':'{0}-{1:.3f}',\n".format('x', q['cost']))
                        hf.write("  'length':{},\n".format(q['cost']))
                        hf.write("  'route':[\n")
                        for lat, lon in list(map(self.router.node_lat_lon, route)):
                            hf.write("[{},{}],\n".format(lat, lon))
                        hf.write("  ],\n")
                        hf.write("  },\n")
                    hf.write("];\n")
            except:
                pass

        def _queue_insert(queue_item):
            nonlocal _queue
            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["cost"] < queue_item["cost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

        def dist(a,b):
            return distance(self.router.rnodes[a], self.router.rnodes[b])

        segments = {}

        # Define function that addes to the queue
        def _add_to_queue(item_start, item_end, branch, queue_so_far, item_weight=1):
            """Add another potential route to the queue"""
            nonlocal _queue, _closeNode, segments

            if (item_start, item_end) not in segments:
                s = item_start
                e = item_end
                d = distance(self.router.rnodes[s], self.router.rnodes[e])
                r = (e,)
                while len(self.router.routing[e])==2:
                    z = s
                    s = e
                    k = list(self.router.routing[e].keys())
                    k.remove(z)
                    e = k[0]
                    d += distance(self.router.rnodes[s], self.router.rnodes[e])
                    r += (e,)
                segments[(item_start, item_end)] = (d, r)

            segment_distance, segment_nodes = segments[(item_start, item_end)]

            # Do not cross
            if segment_nodes[-1] in queue_so_far[branch]["nodes"] or segment_nodes[-1] in queue_so_far['right' if branch=='left' else 'left']["nodes"][:-1]:
               return

            edge_cost = segment_distance

            total_cost = queue_so_far[branch]["cost"] + edge_cost

            all_nodes = queue_so_far[branch]["nodes"] + segment_nodes


            # Create a hash for all the route's attributes
            queue_item = {
                "left": queue_so_far["left"] if branch=="right" else {"cost":total_cost, "nodes":all_nodes},
                "right": queue_so_far["right"] if branch=="left" else {"cost":total_cost, "nodes":all_nodes}
            }
            queue_item["cost"] = queue_item['left']['cost'] + queue_item['right']['cost']

            if self.if_route_exists(queue_item["left"]['nodes'][-1], queue_item["right"]['nodes'][-1],list(queue_item["left"]['nodes'][:-1]+queue_item["right"]['nodes'][:-1])):
                _queue_insert(queue_item)

        def dichotomie(function, max_ecart=0.0005):
            step = 0.5
            x = 1
            ecart = function(x)
            while math.fabs(ecart) > max_ecart:
                if ecart > 0:
                    x = x + step
                else:
                    x = x - step
                step /= 2
                ecart = function(x)
            return x

        start_latlon = self.router.rnodes[start]
        dlat = dichotomie(lambda x: config["distance"] - distance(start_latlon, (start_latlon[0]+x, start_latlon[1])))
        dlon = dichotomie(lambda x: config["distance"] - distance(start_latlon, (start_latlon[0], start_latlon[1]+x)))

        self.router.get_area_rect(start_latlon[0]-dlat, start_latlon[1]-dlon, start_latlon[0]+dlat, start_latlon[1]+dlon)

        # remove all rnodes not in limits
        boundary_nodes = []
        print(len(self.router.routing))
        for node in self.router.rnodes:
                if distance(start_latlon, self.router.rnodes[node])>config["distance"]:
                    for n in self.router.routing[node]:
                        self.router.routing[n].pop(node)
                        if n not in boundary_nodes:
                            boundary_nodes.append(n)
                    self.router.routing.pop(node)
        print(len(self.router.routing))

        # remove impasse
        while len(boundary_nodes)>0:
            node = boundary_nodes.pop()
            if node in self.router.routing:
                if len(self.router.routing[node])==1:
                    for n in self.router.routing[node]:
                        self.router.routing[n].pop(node)
                        if n not in boundary_nodes:
                            boundary_nodes.append(n)
                        self.router.routing.pop(node)
        print(len(self.router.routing))


        # Start by queueing all outbound links from the start node
        if start not in self.router.routing:
            raise KeyError("node {} doesn't exist in the graph".format(start))

        from itertools import combinations
        for comb in combinations(list(self.router.routing[start]) ,2):
            queue_item = {
                "left": {"cost":dist(start, comb[0]), "nodes":(start, comb[0])},
                "right": {"cost":dist(start, comb[1]), "nodes":(start, comb[1])}
            }
            queue_item["cost"] = queue_item['left']['cost'] + queue_item['right']['cost']
            _queue_insert(queue_item)



        # Limit for how long it will search
        count = 0
        while _queue and not self._exit:
            count += 1
            _closeNode = True
            if count%10000==0:
                _export_queue(_longest_route)

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            next_item = _queue.pop(0)

            if next_item['left']['cost']<next_item['right']['cost']:
                consider_branch = 'left'
                other_branch = 'right'
            else:
                consider_branch = 'right'
                other_branch = 'left'
            considered_node = next_item[consider_branch]["nodes"][-1]

            # Found the end node - success
            if considered_node == next_item[other_branch]["nodes"][-1] and len(next_item[other_branch]["nodes"])>1:
                _export_queue(next_item)
                if next_item['cost'] > config['target_dist']:
                    print(next_item)
                    return "success", next_item["left"]["nodes"] + next_item["right"]["nodes"][::-1]
                else:
                    if not _longest_route or next_item['cost'] > _longest_route['cost']:
                        self._min_route = ','.join(str(a) for a in (next_item["left"]["nodes"] + next_item["right"]["nodes"][::-1]))
                        self.min_length = next_item['cost']
                        print("Find new longest route: {:.03}km ({})".format(next_item['cost'], len(_queue)))
                        _longest_route =  next_item # [int(i) for i in next_item["nodes"].split(",")]
                continue

            # If no, add all possible nodes from x to queue
            elif considered_node in self.router.routing:
                for next_node, weight in list(self.router.routing[considered_node].items()):
                    _add_to_queue(considered_node, next_node, consider_branch, next_item, weight)


        if _longest_route:
            print(count)
            _export_queue(_longest_route)
            return "success", _longest_route["left"]["nodes"] + _longest_route["right"]["nodes"][::-1]
        return "gave_up", []

    def generate_gpx(self, file_name, gpx_name):
        if self.min_route:
            return self.min_route.to_gpx(file_name, gpx_name)
        else:
            return False




if __name__ == '__main__':
    from pprint import pprint
    # import time
    # tiles_to_kml(['8251_5613', '8251_5614', '8249_5615'], "debug/test.kml", "test")
    rs = RouteServer()
    # print(computeMissingKml(open("missing_tiles.kml", "rb")))

    pprint(rs.start_route('foot', [49.019971703799264,1.3924220186037095],
                        [49.213139772606155,1.3080430607664086],
                        [], config={'route_mode':'isochrone-dist', 'distance':1.0, 'target_dist':15,
                                               'turnaround_cost':1.5}, thread=False)[1])

    exit()
    pprint(rs.start_route('foot', [49.213139772606155,1.3080430607664086],
                        [49.213139772606155,1.3080430607664086],
                        [], config={'route_mode':'isochrone-dist', 'distance':1.0, 'target_dist':10,
                                               'turnaround_cost':1.5}, thread=False)[1])

    # print(rs.start_route([49.250775603162886,1.4452171325683596],
    #                     [49.250775603162886,1.4452171325683596],
    #                     ["8257_5607", "8257_5610"], thread=False).min_route.routeLatLons)
    # pprint(minDists)
    # #print(rs.start_route([49.250775603162886,1.4452171325683596],
    #                      [49.250775603162886,1.4452171325683596],
    #                      [205,206], thread=False).min_route.getCoords(rs.myRouter.router))
    # print(rs.start_route([49.250775603162886,1.4452171325683596],
    #                     [49.250775603162886,1.4452171325683596],
    #                     [-1], thread=False).min_route.getCoords(rs.myRouter.router))

    # start_time = time.time()
    # rs.start_route([49.01467940545091,1.389772879538316],
    #               [49.00386989926282,1.3952660758713222], [546,580], thread=False)
    # compute_time = time.time()-start_time
    # print("compute time:", compute_time)
    # start_time = time.time()
    # print(rs.start_route([49.01467940545091,1.389772879538316],
    #                     [49.00386989926282,1.3952660758713222],
    #                     [546,580], thread=False).min_route.getCoords(rs.myRouter.router))
    # compute_time = time.time()-start_time
    # print("compute time:", compute_time)

    # myRouter = rs.start_route([49.01467940545091,1.389772879538316],
    #                          [49.00386989926282,1.3952660758713222], [546,580], thread=True)
    # while not myRouter.isComplete:
    # pass
    # print(myRouter.min_route.getCoords(rs.myRouter.router))
