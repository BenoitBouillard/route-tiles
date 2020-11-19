#!/usr/bin/python
# -*- coding: utf-8 -*-

import threading
from pathlib import Path
from pprint import pprint

import gpxpy
import gpxpy.gpx
from fastkml import kml, styles
from shapely.geometry import Point, Polygon, LinearRing
from itertools import permutations, combinations
from copy import deepcopy

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


def export_queue(router, _queue, tag_length="cost", tag_name="cost", new_item=None):
    def default_name(q):
        return '{:.3f}'.format(q[tag_name])
    if isinstance(tag_name, str):
        fct_name = default_name
    else:
        fct_name = tag_name

    def write_item(hf, q):
        route = [i for i in q['nodes']]
        hf.write(" { \n")
        hf.write("  'name':'{}',\n".format(fct_name(q)))
        hf.write("  'length':{},\n".format(q[tag_length]))
        hf.write("  'route':[\n")
        for lat, lon in list(map(router.node_lat_lon, route)):
            hf.write("[{},{}],\n".format(lat, lon))
        hf.write("  ],\n")
        hf.write("  },\n")

    with open('debug/routes.js', 'w') as hfile:
        hfile.write("var routes = [\n")
        if new_item:
            write_item(hfile, new_item)
        for q in _queue[:100]:
            write_item(hfile, q)
        hfile.write("];\n")


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

    def dist(self, a,b):
        return distance(self.router.rnodes[a], self.router.rnodes[b])

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

        segments = {}
        segment_cuts = [start]
        for z in zones:
            for e in z.entryNodeId:
                segments.append(e.nodeId)

        def find_segment(item_start, item_end):
            nonlocal segments

            if (item_start, item_end) not in segments:
                s = item_start
                e = item_end
                d = 0
                r = ()
                while True:
                    e_latlon = self.router.rnodes[e]
                    d += distance(self.router.rnodes[s], e_latlon)
                    r += (e,)
                    keys = list(filter(lambda k: k != s, self.router.routing[e].keys()))
                    if len(keys) != 1:
                        break
                    s = e
                    e = keys[0]
                    if e in segment_cuts:
                        break


                segments[(item_start, item_end)] = (d, r)
            return segments[(item_start, item_end)]


        def _export_queue(new_item=None):
            def name(i):
                return '{0}-{1:.3f}'.format(len(i['not_visited_zones']), i['heuristic_cost'])
            export_queue(self.router, _queue, tag_length="cost", tag_name=name, new_item=new_item)

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

    def do_route_isochrone(self, start, config):
        """Do the routing"""
        _queue = []
        _longest_route = None

        def _export_queue(new_item=None):
            export_queue(self.router, _queue, tag_length="cost", tag_name="hcost", new_item=new_item)

        def dist(a,b): return self.dist(a, b)

        # Load area of the circle to be sure to have all routes
        start_latlon = self.router.rnodes[start]
        dlat = dichotomie(lambda x: config["radius"] - distance(start_latlon, (start_latlon[0]+x, start_latlon[1])))
        dlon = dichotomie(lambda x: config["radius"] - distance(start_latlon, (start_latlon[0], start_latlon[1]+x)))
        self.router.get_area_rect(start_latlon[0]-dlat, start_latlon[1]-dlon, start_latlon[0]+dlat, start_latlon[1]+dlon)

        def find_segment(item_start, item_end):
            s = item_start
            e = item_end
            d = 0
            r = ()
            while True:
                e_latlon = self.router.rnodes[e]
                dist = distance(start_latlon, e_latlon)
                if dist > config["radius"]:
                    return None, None
                d += distance(self.router.rnodes[s], e_latlon)
                r += (e,)
                if e is start:
                    break
                keys = list(filter(lambda k: k != s, self.router.routing[e].keys()))
                if len(keys) != 1:
                    break
                s = e
                e = keys[0]

            return d, r

        def limit_links(loc_links, nodes):
            lks = {}
            external_route_count = 0
            boundaries_nodes = set()
            for n in nodes:
                lks[n] = []
                for l in loc_links[n]:
                    if l[0] in nodes:
                        lks[n].append(l)
                    else:
                        external_route_count += 1
                        boundaries_nodes.add(n)
            return lks, external_route_count, boundaries_nodes

        def find_longest_route(start, stop, loc_links):
            """Do the routing"""
            _loc_queue = []

            def _export_queue(new_item=None):
                export_queue(self.router, _loc_queue, tag_length="cost", tag_name="cost", new_item=new_item)

            def _loc_queue_insert(queue_item):
                nonlocal _loc_queue
                # Try to insert, keeping the queue ordered by decreasing heuristic cost
                position = 0
                for test in _loc_queue:
                    if test["cost"] > queue_item["cost"]:
                        _loc_queue.insert(position, queue_item)
                        break
                    position += 1

                else:
                    _loc_queue.append(queue_item)

            # Define function that addes to the queue
            def _loc_add_to_queue(item_end, queue_so_far):
                """Add another potential route to the queue"""
                last_node, segment_distance, segment_nodes, segment_link_nodes = item_end
                total_cost = queue_so_far["cost"] + segment_distance
                # Create a hash for all the route's attributes
                queue_item = {
                    "cost": total_cost,
                    "nodes": queue_so_far["nodes"] + segment_nodes,
                    "node" : last_node,
                    "link_nodes": queue_so_far["link_nodes"] | segment_link_nodes
                }
                _loc_queue_insert(queue_item)

            if start == stop:
                return {"cost": 0, "nodes": (start,), 'link_nodes':set([start])}
            else:
                for linkedNode in loc_links[start]:
                    _loc_add_to_queue(linkedNode, {'cost': 0, 'nodes': (start,), 'link_nodes': set([start])})

            # Limit for how long it will search
            longest = None
            while _loc_queue and not self._exit:
                #_export_queue(longest)
                next_item = _loc_queue.pop(0)
                considered_node = next_item["node"]
                if considered_node == stop:
                    if longest is None or next_item['cost']>longest['cost']:
                        longest = next_item
                    continue
                for next_node in loc_links[considered_node]:
                    if next_node[0] not in next_item['link_nodes']:
                        _loc_add_to_queue(next_node, next_item)
            longest['link_nodes'].remove(start)
            return longest

        def export_links(links):
            def write_item(hf, q, l):
                route = (l,) + q[2]
                hf.write(" { \n")
                hf.write("  'name':'{0}-{1}',\n".format(route[0], route[-1]))
                hf.write("  'length':{},\n".format(q[1]))
                hf.write("  'route':[\n")
                for lat, lon in list(map(self.router.node_lat_lon, route)):
                    hf.write("[{},{}],\n".format(lat, lon))
                hf.write("  ],\n")
                hf.write("  },\n")

            with open('debug/links.js', 'w') as hfile:
                hfile.write("var links = [\n")
                for l in links:
                    for r in links[l]:
                        write_item(hfile, r, l)
                hfile.write("];\n")

        def find_links():
            links = {}
            links_r = {}
            _nodes = [start]
            while _nodes:
                node = _nodes.pop()
                links[node] = []
                for next_node in self.router.routing[node]:
                    segment = find_segment(node, next_node)
                    if segment[0] is None:
                        continue
                    last_node = segment[1][-1]
                    if last_node == node:
                        continue
                    segment = (last_node, segment[0], segment[1], set([last_node]))
                    links[node].append(segment)
                    if last_node not in links:
                        _nodes.append(last_node)
                    if last_node not in links_r:
                        links_r[last_node] = set([])
                    links_r[last_node].add(node)
            print(len(links), sum([len(i) for i in links.values()]))
            # Remove dead end
            find = True
            while find:
                find = False
                # merge
                export_links(links)
                for node in list(links.keys()):
                    if node is start:
                        continue
                    if len(links[node]) == 2 and len(links_r[node]) == 2:
                        # assume segments are reversible (no single way)
                        l1 = links[node][0][0]
                        l2 = links[node][1][0]
                        for l in range(len(links[l1])):
                            if links[l1][l][0] == node:
                                link1 = links[l1].pop(l)
                                break
                        for l in range(len(links[l2])):
                            if links[l2][l][0] == node:
                                link2 = links[l2].pop(l)
                                break
                        links_r[l1].remove(node)
                        links_r[l2].remove(node)
                        if l1 == l2:
                            print("Remove loop ", node)
                        else:
                            nodes1 = link1[2] + links[node][1][2]
                            dista1 = link1[1] + links[node][1][1]
                            nodes2 = link2[2] + links[node][0][2]
                            dista2 = link2[1] + links[node][0][1]
                            links[l1].append((l2, dista1, nodes1, set([l2])))
                            links[l2].append((l1, dista2, nodes2, set([l1])))
                            links_r[l1].add(l2)
                            links_r[l2].add(l1)
                            print("Merge to skip ", node)
                        links.pop(node)
                        links_r.pop(node)
                        find = True

                # Remove multiple routes
                for node in links:
                    for to_node in set([l[0] for l in links[node]]):
                        li = list(filter(lambda l: l[0] == to_node, links[node]))
                        if len(li) > 1:
                            print("Find multiple route for ", node, to_node)
                            ml = max([l[1] for l in li])
                            links[node] = list(filter(lambda l: l[0] != to_node or l[1] >= ml, links[node]))
                            find = True

                for node in list(links.keys()):
                    if len(set([l[2] for l in links[node]])) == 1:
                        to_node = links[node][0][0]
                        if to_node in links_r[node]:
                            for i in range(len(links[to_node]) - 1, -1, -1):
                                if links[to_node][i][0] == node:
                                    links[to_node].pop(i)
                            print("remove no way node ", node, to_node)
                            links.pop(node)
                            links_r[to_node].remove(node)
                            links_r.pop(node)
                            find = True

            print(len(links), sum([len(i) for i in links.values()]))
            export_links(links)
            return links

        links = find_links()

        def nodes_azimuth(n1, n2):
            return azimuth(self.router.rnodes[n1], self.router.rnodes[n2])

        def find_rings(links):
            rings = []

            def ring_for_nodes(nodes):
                pass

            def find_ring_next_node(nodes):
                az = nodes_azimuth(nodes[-2], nodes[-1])
                min_angle = 360
                next_node = None
                for l in links[nodes[-1]]:
                    if l[0]==nodes[-2]:
                        continue
                    azl = nodes_azimuth(nodes[-1], l[0])
                    angle = (180 + az - azl) % 360
                    if angle < min_angle:
                        min_angle = angle
                        next_node = l[0]
                return next_node


            for n1 in links:
                for l1 in links[n1]:
                    n2 = l1[0]
                    nodes = [n1, n2]
                    while True:
                        nn = find_ring_next_node(nodes)
                        if nn == nodes[0]:
                            ring_str = ','.join([str(n) for n in nodes])
                            for r in rings:
                                if ring_str in r+','+r:
                                    break
                            else:
                                rings.append(ring_str)
                            break
                        nodes.append(nn)

            for i in range(len(rings)):
                rings[i] = set([int(n) for n in rings[i].split((','))])
            return rings

        rings = find_rings(links)
        rings = list(filter(lambda n:start not in n, rings))
        rings_contacts = []
        for i in range(len(rings)):
            rings_contacts.append(set())
            for j in range(len(rings)):
                if i==j: continue
                if len(rings[i] & rings[j])>1:
                    rings_contacts[i].add(j)

        def rings_perm_iter(rings, count):
            def recur(rr, contacts, nodes):
                for r in contacts:
                    if len(rr)+1 < count:
                        rrr = rr | set([r])
                        yield from recur(rrr, (contacts | rings_contacts[r]) - rrr, nodes | rings[r])
                    else:
                        yield nodes | rings[r]

            for r in range(len(rings)):
                if count==1:
                    yield set(rings[r])
                else:
                    yield from recur(set([r]), rings_contacts[r] , set(rings[r]))

        def compute_shortcuts(links):
            # route shortcuts
            shn = set()
            for x in range(config['optim'], 0, -1):
                print("Search for optim level ", x)
                # for p in combinations(rings, x):
                    # p = deepcopy(p)
                    # while len(p)>1:
                    #     for r in p[:-1]:
                    #         if len(r & p[-1])>1:
                    #             r |= p[-1]
                    #             p = p[:-1]
                    #             break
                    #     else:
                    #         break
                    # if len(p)>1:
                    #     continue
                    # lp = p[0]
                for lp in rings_perm_iter(rings, x):
                    if (shn & lp) or (start in lp):
                        continue
                    lks, external_route_count, boundaries_nodes = limit_links(links, lp)
                    if external_route_count <= 3:
                        print(lp, external_route_count)
                        shn |= lp ^ boundaries_nodes
                        # Remove internal links
                        for n in lp:
                            links[n] = list(filter(lambda l: l[0] not in lp, links[n]))
                        for c in permutations(boundaries_nodes, 2):
                            longest = find_longest_route(c[0], c[1], lks)
                            links[c[0]].append((c[1], longest['cost'], longest['nodes'], longest['link_nodes']))

                export_links(links)

            for n in list(links.keys()):
                if len(links[n])==0:
                    links.pop(n)
            return links

        if config['optim']:
            links = compute_shortcuts(links)
        export_links(links)

        print(len(links), sum([len(i) for i in links.values()]))

        radius_center_point = start

        _hct = {}

        def if_route_exists(start, max_length, forbidden_nodes):
            """Do the routing"""
            _closed = forbidden_nodes
            _loc_queue = []

            def _export_queue(new_item=None):
                export_queue(self.router, _loc_queue, tag_length="cost", tag_name="hcost", new_item=new_item)

            def _loc_queue_insert(queue_item):
                nonlocal _loc_queue
                # Try to insert, keeping the queue ordered by decreasing heuristic cost
                position = 0
                for test in _loc_queue:
                    if test["hcost"] > queue_item["hcost"]:
                        _loc_queue.insert(position, queue_item)
                        break
                    position += 1

                else:
                    _loc_queue.append(queue_item)

            # Define function that addes to the queue
            def _loc_add_to_queue(segment, queue_so_far):
                """Add another potential route to the queue"""
                nonlocal _closed
                last_node, segment_distance, segment_nodes, segment_link_nodes = segment

                total_cost = queue_so_far["cost"] + segment_distance
                if last_node not in _hct:
                    _hct[last_node] = distance(self.router.rnodes[last_node], self.router.rnodes[radius_center_point])
                hc = _hct[last_node]
                if total_cost + hc > max_length:
                    return None
                # Create a hash for all the route's attributes
                queue_item = {
                    "cost": total_cost,
                    "hcost": hc,
                    "nodes": queue_so_far["nodes"] + segment_nodes,
                    "node" : last_node,
                }
                _loc_queue_insert(queue_item)
                _closed.add(last_node)

            if start == radius_center_point:
                return {"cost": 0, "nodes": (start,)}

            for linkedNode in links[start]:
                if _closed.isdisjoint(linkedNode[3]) :
                    _loc_add_to_queue(linkedNode, {"cost": 0, "nodes": (start,)})

            # Limit for how long it will search
            while _loc_queue and not self._exit:
                #_export_queue()
                next_item = _loc_queue.pop(0)
                considered_node = next_item["node"]
                if considered_node == radius_center_point:
                    return next_item
                for segment in links[considered_node]:
                    if _closed.isdisjoint(segment[3]):
                        _loc_add_to_queue(segment, next_item)
            else:
                return False

        def _queue_insert(queue_item):
            nonlocal _queue
            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["hcost"] < queue_item["hcost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

        # Define function that adds to the queue
        def _add_to_queue(segment, queue_so_far):
            """Add another potential route to the queue"""
            last_node, segment_distance, segment_nodes, segment_link_nodes = segment

            total_cost = queue_so_far["cost"] + segment_distance

            route_to_close = if_route_exists(last_node,
                                             config['target_dist'] + config['target_threshold'] - total_cost,
                                             queue_so_far["link_nodes"] | segment_link_nodes)

            if route_to_close:
                # Create a hash for all the route's attributes
                queue_item = {
                    "cost": total_cost,
                    "nodes": queue_so_far["nodes"] + segment_nodes,
                    "link_nodes": queue_so_far["link_nodes"] | segment_link_nodes,
                    "hcost" : total_cost + route_to_close['cost'],
                    "node" : last_node,
                }
                _queue_insert(queue_item)


        # Start by queueing all outbound links from the start node
        if start not in self.router.routing:
            raise KeyError("node {} doesn't exist in the graph".format(start))

        if len(links)==1:
            return "gave_up", []

        for next_node in links[start]:
            _add_to_queue(next_node, {'nodes':(start, ), 'cost':0, "link_nodes":set()})

        count = 0
        while _queue and not self._exit:
            count += 1
            if count%250000==0:
                print(count, len(_queue))
                _export_queue(_longest_route)

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            next_item = _queue.pop(0)

            considered_node = next_item["node"]

            # Found the end node - success
            if considered_node == start:
                if next_item['cost'] > config['target_dist']:
                    _export_queue(next_item)
                    print(next_item)
                    return "success", next_item["nodes"]
                else:
                    if not _longest_route or next_item['cost'] > _longest_route['cost']:
                        #_export_queue(next_item)
                        self._min_route = ','.join(str(a) for a in next_item["nodes"])
                        self.min_length = next_item['cost']
                        print("Find new longest route: {:.03}km ({})".format(next_item['cost'], len(_queue)))
                        _longest_route =  next_item
                continue

            #If no, add all possible nodes from x to queue
            for segment in links[considered_node]:
                if next_item['link_nodes'].isdisjoint(segment[3]):
                    _add_to_queue(segment, next_item)

        if _longest_route:
            print(count)
            #pprint(_longest_route)
            _export_queue(_longest_route)
            return "success", _longest_route["nodes"]
        return "gave_up", []

    def generate_gpx(self, file_name, gpx_name):
        if self.min_route:
            return self.min_route.to_gpx(file_name, gpx_name)
        else:
            return False


if __name__ == '__main__':
    # import time
    # tiles_to_kml(['8251_5613', '8251_5614', '8249_5615'], "debug/test.kml", "test")
    # print(computeMissingKml(open("missing_tiles.kml", "rb")))

    rs = RouteServer()
    durations = []
    for i in range(0,1):
        start_time = time.time()
        rs.start_route('trail', [49.16091, 1.33688],
                       [49.16091, 1.33688],
                       [], config={'route_mode': 'isochrone-dist', 'radius': 0.45, 'target_dist': 100.0,
                                   'target_threshold': 0.4, 'optim':6,
                                   'turnaround_cost': 1.5}, thread=False)  # GAILLON
        compute_time = time.time()-start_time
        rs.generate_gpx('debug/debug.gpx', 'isochrone')
        durations.append(compute_time)
        print("compute time:", compute_time)
    print("avg: {:.02f} |".format(sum(durations)/len(durations)), ', '.join(["{:.02f}".format(d) for d in durations]))

    #length: 3.196987669233947
    #avg: 9.68 | 10.05, 9.47, 9.38, 10.15, 9.58, 9.68, 9.68, 9.64, 9.58, 9.61

# MUMU 1km
    # PC Boulot :                 2.52, 1.93, 1.99, 2.05, 2.07, 2.00, 2.05, 2.06, 2.03, 2.03
    #    16/11 10:00  avg: 0.89 | 1.34, 0.82, 0.80, 0.83, 0.83, 0.90, 0.82, 0.85, 0.84, 0.84
    #          16:00  avg: 0.84 | 1.18, 0.79, 0.87, 0.78, 0.77, 0.80, 0.81, 0.77, 0.80, 0.83
    # MBA'17    :
    # MBP'M1    :

    # GAILLON 0.3km => 3.17km
    # PC Boulot :
    #    17/11 13:00  avg: 16.32 | 17.98, 17.01, 16.13, 15.73, 15.87, 16.07, 16.00, 16.02, 16.34, 16.06 => 1264579 iter
    #      shortcuts  avg: 0.62 | 1.00, 0.60, 0.61, 0.57, 0.57, 0.57, 0.57, 0.57, 0.57, 0.60            =>   33246 iter
    # MBA'17    :
    # MBP'M1    :
    # Optim 0 : 47/144

    # GAILLON 0.26 opt 0 2.750km: 30.29s (44/122 => 2753838)
    # GAILLON 0.26 opt 3 2.750km:  1.62s (40/122 =>   63167)
    # GAILLON 0.26 opt 5 2.750km:  0.94s (36/110 =>   40323)
    # GAILLON 0.26 opt 6 2.750km:  1.10s (34/102 =>   28363)
    # GAILLON 0.26 opt 7 2.750km:  2.71s (33/100 =>   27676)

    # GAILLON 0.27 opt 0 2.830071101913692km: 36.49s (40/122 => 2753838)
    # GAILLON 0.27 opt 7 2.830071101913692km:  2.81s (33/100 =>   35038)

    # GAILLON 0.3 opt 0 3.196km:    149.46s (47/144 => 28219608)
    # GAILLON 0.3 opt 3 3.196km:  16.80s (47/144 =>  1126167)
    # GAILLON 0.3 opt 7 3.196km:   3.15s (38/116 =>    27463)
    # GAILLON 0.3 ring5 3.196km:   2.03s (34/102 =>    46272)
    # GAILLON 0.32 opt 7 3.29km:   6.61s (44/134 =>   193826)
    # GAILLON 0.33 opt 7 3.45km:  24.17s (51/156 =>  1488351)
    # GAILLON 0.34 opt 7 4.16km:  66.84s (57/174 =>  4629232) 1x5 + 6x3
    # GAILLON 0.34 opt 12 4.16km: 46.03s (50/152 =>   521847) 1x12 + 6x3
    # GAILLON 0.34 ring5 4.16km:   5.66s (36/110 =>    40672) 1x20 + 1x9 + 3x3
    # GAILLON 0.34 opt 12 4.16km: 16.86s  (44/134 =>   81983) 1x12  1x9 + 5x3
    # GAILLON 0.38 opt 7 4.73km:  334.8s (61/186 => 23355940) 1x5 + 6x3       /!\ prev
    # GAILLON 0.38 opt 9 4.73km:  61.01s (55/168 =>  3883343) 1x9 + 1x5 + 5x3  2,5K-2
    # GAILLON 0.38 ring5 4.73km:   7.34s (42/128 =>   140345) 1x18 + 1x9 + 4x3  2,5K-2

    # GAILLON 0.40 opt 9       5.20km:  4093s (66/202 => 293069242) 1x5 + 5x3
    # GAILLON 0.40 opt 5 rings 5.20km: 147.4s (53/162 =>  18912637) 1x18 + 4x3
    # GAILLON 0.40 ring5       5.20km: 149.8s (53/162 =>  10255519) 1x18 + 4x3

    # GAILLON 0.45 ring5       km:  (72/218 =>  ) 1x7 + 1x5 + 1x4 + 6x3





    exit()
    rs.start_route('trail', [49.213139, 1.308043], [49.213139, 1.308043], [],
                   config={'route_mode': 'isochrone-dist', 'radius': 1.0, 'target_dist': 100.0,
                           'target_threshold': 0.2,
                           'optim': False,
                           'turnaround_cost': 1.5}, thread=False)  # MUMU

    pprint(rs.start_route('roadcycle', [49.16091,1.33688],
                        [49.16091,1.33688],
                        [], config={'route_mode':'isochrone-dist', 'radius':0.3, 'target_dist':5.0, 'target_threshold':0.2,
                                               'turnaround_cost':1.5}, thread=False)[1]) #GAILLON
    pprint(rs.start_route('trail', [49.213139772606155,1.3080430607664086],
                        [49.213139772606155,1.3080430607664086],
                        [], config={'route_mode':'isochrone-dist', 'radius':1.0, 'target_dist':15.0, 'target_threshold':0.2,
                                               'turnaround_cost':1.5}, thread=False)[1].route) # MUMU
    pprint(rs.start_route('footroad', [49.019971703799264,1.3924220186037095],
                        [49.213139772606155,1.3080430607664086],
                        [], config={'route_mode':'isochrone-dist', 'radius':0.6, 'target_dist':5.0, 'target_threshold':0.2,
                                               'turnaround_cost':1.5}, thread=False)[1]) # PACY
    pprint(rs.start_route('trail', [49.213139772606155,1.3080430607664086],
                        [49.213139772606155,1.3080430607664086],
                        [], config={'route_mode':'isochrone-dist', 'radius':0.5, 'target_dist':15.0, 'target_threshold':0.2,
                                               'turnaround_cost':1.5}, thread=False)[1].route)
    pprint(rs.start_route('footroad', [49.019854,1.389280],
                        [49.213139772606155,1.3080430607664086],
                        [], config={'route_mode':'isochrone-dist', 'radius':0.1, 'target_dist':5.0, 'target_threshold':0.2,
                                               'turnaround_cost':1.5}, thread=False)[1])


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
