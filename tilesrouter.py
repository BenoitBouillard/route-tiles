#!/usr/bin/python
# -*- coding: utf-8 -*-

import threading
from pathlib import Path

import gpxpy
import gpxpy.gpx
from fastkml import kml, styles

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


class MyRouter(object):
    def __init__(self, router, start, end, tiles, config):
        self.router = router
        self._min_route = None
        self.min_length = None
        self._exit = False
        self._complete = False
        self.start = start
        self.end = end
        self.tiles = tiles
        self.progress = 100.0
        self.config = config

        debug_export_tiles(tiles)

    def abort(self):
        self._exit = True

    @property
    def is_complete(self):
        return self._complete

    def run(self):
        self.min_length = None
        self._min_route = None

        status, r = self.do_route_with_crossing_zone(self.start.nodeId, self.end.nodeId,
                                                     frozenset(self.tiles), self.config)
        if status != "success":
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
            if config['turnaround_cost']>0:
                queue_so_far_nodes = queue_so_far["nodes"].split(',')
                if len(queue_so_far_nodes)>2:
                    if str(item_end) == queue_so_far_nodes[-2]:
                        _export_queue(queue_so_far)
                        print("Turnaround cost")
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

            # If we do, and known total_cost to end is lower we can ignore the queueSoFar path
            if end_queue_item and end_queue_item["cost"] < total_cost:
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

            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            position = 0
            for test in _queue:
                if test["heuristic_cost"] > queue_item["heuristic_cost"]:
                    _queue.insert(position, queue_item)
                    break
                position += 1

            else:
                _queue.append(queue_item)

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
            # _export_queue()

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

            for zone in not_visited_zones:
                if considered_node in zone.entry_nodes_id:
                    not_visited_zones = not_visited_zones - {zone}

            # If we already visited the node, ignore it
            if (considered_node, not_visited_zones) in _closed:
                continue

            # Found the end node - success
            if considered_node == end:
                if len(not_visited_zones) == 0:
                    _export_queue(next_item)
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

    def generate_gpx(self, file_name, gpx_name):
        if self.min_route:
            return self.min_route.to_gpx(file_name, gpx_name)
        else:
            return False


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
        self.myRouter = None
        self.mode = None
        self.thread = None

    def start_route(self, mode, start_loc, end_loc, tiles, config={}, thread=True):
        print(tiles)

        if thread and self.myRouter and not self.myRouter.is_complete:
            print("Abord previous route...")
            self.myRouter.abort()
            self.thread.join()
            print("   ...OK")
        if mode != self.mode:
            self.mode = mode
            self.stored_tiles = {}
            self.router = Datastore(mode, cache_dir=str(Path.home().joinpath('.tilescache')))
        coord_dict = CoordDict(self.router)
        start_point = coord_dict.get(*start_loc)
        end_point = coord_dict.get(*end_loc)
        selected_tiles = []
        for t in tiles:
            if t not in self.stored_tiles:
                self.stored_tiles[t] = Tile(t)
            selected_tiles.append(self.stored_tiles[t])
            self.stored_tiles[t].get_entry_points(self.router)
            if not self.stored_tiles[t].entryNodeId:
                return False, "No entry point for tiles", [t]

        self.myRouter = MyRouter(self.router, start_point, end_point, selected_tiles, config)
        if thread:
            self.thread = threading.Thread(target=self.myRouter.run)
            # Background thread will finish with the main program
            self.thread.setDaemon(True)
            # Start YourLedRoutine() in a separate thread
            self.thread.start()

        else:
            self.myRouter.run()

        return self.myRouter, self.is_complete, self.route

    @property
    def progress(self):
        return self.myRouter.progress

    @property
    def route(self):
        return self.myRouter.min_route

    @property
    def is_complete(self):
        return self.myRouter.is_complete


if __name__ == '__main__':
    from pprint import pprint
    # import time
    # tiles_to_kml(['8251_5613', '8251_5614', '8249_5615'], "debug/test.kml", "test")
    rs = RouteServer()
    # print(computeMissingKml(open("missing_tiles.kml", "rb")))

    pprint(rs.start_route('roadcycle', [48.96603327300286,1.6886383442175525],
                        [48.967230660169,1.6828179895699071],
                        ['8268_5629'], config={'turnaround_cost':1}, thread=False)[2].route)

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
