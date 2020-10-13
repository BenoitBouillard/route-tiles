#!/usr/bin/python
# -*- coding: utf-8 -*-

from fastkml import kml, styles
from tile import Tile, CoordDict, coordFromTile
from pyroutelib3 import Datastore
import os
from pathlib import Path
from mathutils import *
import threading
import gpxpy
import gpxpy.gpx

def LatLonsToGpx(latlons, filename, name):
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

def TilesToKml(tiles, filename, name):
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
        p.geometry =  tile.lineStringLonLat
        f.append(p)
        
    print(k.to_string(prettyprint=True))
    with open(filename, 'w') as hf:
        hf.write(k.to_string(prettyprint=True))
    return True


class Route(object):
    def __init__(self, route, router):
        self.route = route
        self.routeLatLons = list(map(router.nodeLatLon, route))
        self.computeLength(self.routeLatLons)
        self.length = self.computeLength(self.routeLatLons)


    @staticmethod
    def computeLength(routeLatLons):
        length = 0
        previous = routeLatLons[0]
        for latlon in routeLatLons[1:]:
            length += distance(previous, latlon)
            previous = latlon
        return length


    def toGpx(self, filename, name):
        return LatLonsToGpx(self.routeLatLons, filename, name)


class MyRouter(object):
    def __init__(self, router, start, end, tiles):
        self.router = router
        self._min_route = None
        self.min_length = None
        self._exit = False
        self._complete = False
        self.start = start
        self.end = end
        self.tiles = tiles
        self.progress = 100.0
        def _exportTiles(tiles):
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
        _exportTiles(tiles)

    def abort(self):
        self._exit = True

    @property
    def isComplete(self):
        return self._complete

    def run(self):
        self.min_length = None
        self._min_route = None

        status, r = self.doRouteWithCrossingZone(self.start.nodeId, self.end.nodeId, frozenset(self.tiles))
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
        if self._min_route is None: return None
        if isinstance(self._min_route, str):
            self._min_route = Route([int(i) for i in self._min_route.split(",")], router=self.router)
        return self._min_route
    
    def doRouteWithCrossingZone(self, start, end, zones):
        """Do the routing"""
        _closed = {(start, frozenset(zones))}
        _queue = []
        _closeNode = True
        _end = end
        minDists = {}
        minDistsFast = {}

        def _exportQueue(nextItem=None):
            nonlocal _closed, _queue, _closeNode
            with open('debug/routes.js', 'w') as hf:
                hf.write("var routes = [\n")
                if nextItem:
                    route = [int(i) for i in nextItem["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0}-{1:.3f}',\n".format(len(nextItem['notVisitedZones']), nextItem['heuristicCost']))
                    hf.write("  'length':{},\n".format(nextItem['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.nodeLatLon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                for q in _queue:
                    route = [int(i) for i in q["nodes"].split(",")]
                    hf.write(" { \n")
                    hf.write("  'name':'{0}-{1:.3f}',\n".format(len(q['notVisitedZones']), q['heuristicCost']))
                    hf.write("  'length':{},\n".format(q['cost']))
                    hf.write("  'route':[\n")
                    for lat, lon in list(map(self.router.nodeLatLon, route)):
                        hf.write("[{},{}],\n".format(lat, lon))
                    hf.write("  ],\n")
                    hf.write("  },\n")
                hf.write("];\n")

        # Define function that addes to the queue
        def _addToQueue(start, notVisitedZones, end, queueSoFar, weight=1):
            """Add another potential route to the queue"""
            nonlocal _closed, _queue, _closeNode, minDists, minDistsFast

            # Assume start and end nodes have positions
            if end not in self.router.rnodes or start not in self.router.rnodes:
                return

            # Get data around end node
            self.router.getArea(self.router.rnodes[end][0], self.router.rnodes[end][1])

            # Ignore if route is not traversible
            if weight == 0:
                return

            # Do not turn around at a node (don't do this: a-b-a)
            # if len(queueSoFar["nodes"].split(",")) >= 2 and queueSoFar["nodes"].split(",")[-2] == str(end):
            #    return

            edgeCost = distance(self.router.rnodes[start], self.router.rnodes[end]) / weight
            totalCost = queueSoFar["cost"] + edgeCost
                
            def _minDist(start, tiles, end, store=True, fast=False):
                nonlocal minDists, minDistsFast
                if self._exit: return 0
                md = minDistsFast if fast else minDists
                ### compute flyby min distance by visiting all tiles
                if len(tiles)==0:
                    return distance(start, end)
                    
                if (start, frozenset(tiles), end) in md:
                    return md[(start, frozenset(tiles), end)]
                    
                min_dist = None
                for t in tiles:
                    remain_tiles = set(tiles)-{t}
                    if fast and len(t.entryNodeId)>4:
                        ep = t.edges
                    else:
                        ep = [n.latlon for n in t.entryNodeId]
                    for entry in ep:
                        pa = distance(start, entry)
                        pb = _minDist(entry, remain_tiles, end, fast=fast)
                        if min_dist is None or pa+pb<min_dist: min_dist = pa+pb
                if store:
                    md[(start, frozenset(tiles), end)] = min_dist
                return min_dist
                
            # t = time.time() if len(minDists)==0 else None
            hc = _minDist(self.router.rnodes[end],notVisitedZones, self.router.rnodes[_end], False, len(notVisitedZones)>5)
            # if t:
                # print("min dist time:{}".format(time.time()-t))
            heuristicCost = totalCost + hc

            allNodes = queueSoFar["nodes"] + "," + str(end)

            # Check if path queueSoFar+end is not forbidden
            for i in self.router.forbiddenMoves:
                if i in allNodes:
                    _closeNode = False
                    return

            # Check if we have a way to 'end' node
            endQueueItem = None
            for i in _queue:
                if (i["end"], i["notVisitedZones"]) == (end, notVisitedZones):
                    endQueueItem = i
                    break

            # If we do, and known totalCost to end is lower we can ignore the queueSoFar path
            if endQueueItem and endQueueItem["cost"] < totalCost:
                return

            # If the queued way to end has higher total cost, remove it (and add the queueSoFar scenario, as it's cheaper)
            elif endQueueItem:
                _queue.remove(endQueueItem)

            # Check against mandatory turns
            forceNextNodes = None
            if queueSoFar.get("mandatoryNodes", None):
                forceNextNodes = queueSoFar["mandatoryNodes"]

            else:
                for activationNodes, nextNodes in self.router.mandatoryMoves.items():
                    if allNodes.endswith(activationNodes):
                        _closeNode = False
                        forceNextNodes = nextNodes.copy()
                        break

            # Create a hash for all the route's attributes
            queueItem = {
                "cost": totalCost,
                "heuristicCost": heuristicCost,
                "nodes": allNodes,
                "end": end,
                "notVisitedZones": notVisitedZones,
                "mandatoryNodes": forceNextNodes
            }

            # Try to insert, keeping the queue ordered by decreasing heuristic cost
            count = 0
            for test in _queue:
                if test["heuristicCost"] > queueItem["heuristicCost"]:
                    _queue.insert(count, queueItem)
                    break
                count += 1

            else:
                _queue.append(queueItem)

        # Start by queueing all outbound links from the start node
        if start not in self.router.routing:
            raise KeyError("node {} doesn't exist in the graph".format(start))

        elif start == end and not zones:
            return "no_route", []

        else:
            notVisitedZones = frozenset(zones)
            for linkedNode in list(self.router.routing[start]):
                weight = self.router.routing[start][linkedNode]
                _addToQueue(start, notVisitedZones, linkedNode, {"cost": 0, "nodes": str(start)}, weight)

        # Limit for how long it will search
        count = 0
        while count < 1000000 and not self._exit:
            count += 1
            _closeNode = True
            # _exportQueue()

            # Pop first item from queue for routing. If queue it's empty - it means no route exists
            if len(_queue) > 0:
                nextItem = _queue.pop(0)
            else:
                return "no_route", []

            consideredNode = nextItem["end"]
            notVisitedZones = nextItem["notVisitedZones"]

            if not self.min_length or nextItem['cost'] > self.min_length:
                self.min_length = nextItem['cost']
                self._min_route = nextItem['nodes']
                self.progress = 100.0 * nextItem['cost'] / nextItem['heuristicCost']
                print_progress_bar(nextItem['cost'], nextItem['heuristicCost'])


            for zone in notVisitedZones:
                if consideredNode in zone.entryNodesId:
                    notVisitedZones = notVisitedZones - {zone}

            # If we already visited the node, ignore it
            if (consideredNode, notVisitedZones) in _closed:
                continue

            # Found the end node - success
            if consideredNode == end:
                if len(notVisitedZones) == 0:
                    _exportQueue(nextItem)
                    return "success", [int(i) for i in nextItem["nodes"].split(",")]

            # Check if we preform a mandatory turn
            if nextItem["mandatoryNodes"]:
                _closeNode = False
                nextNode = nextItem["mandatoryNodes"].pop(0)
                if consideredNode in self.router.routing and nextNode in self.router.routing.get(consideredNode, {}).keys():
                    _addToQueue(consideredNode, notVisitedZones, nextNode, nextItem,
                                self.router.routing[consideredNode][nextNode])

            # If no, add all possible nodes from x to queue
            elif consideredNode in self.router.routing:
                for nextNode, weight in list(self.router.routing[consideredNode].items()):
                    if (nextNode, notVisitedZones) not in _closed:
                        _addToQueue(consideredNode, notVisitedZones, nextNode, nextItem, weight)

            if _closeNode:
                _closed.add((consideredNode, notVisitedZones))

        else:
            return "gave_up", []


    def generateGpx(self, fileName, gpxName):
        if self.min_route:
            return self.min_route.toGpx(fileName, gpxName)
        else:
            return False


def computeMissingKml(file):
    k = kml.KML()
    doc=file.read()
    try:
        k.from_string(doc)
    except Exception as e:
        print(e)
        return False

    features = list(k.features())
    folder = list(features[0].features())[0]
    #folder = features[0]
    xmin, xmax, ymin, ymax = None, None, None, None
    not_found_tiles = []
    for placemark in folder.features():
        tile = Tile(placemark.geometry.coords)
        not_found_tiles.append(tile.uid)
        if not xmin or tile.x<xmin: xmin=tile.x
        if not xmax or tile.x>xmax: xmax=tile.x
        if not ymin or tile.y<ymin: ymin=tile.y
        if not ymax or tile.y>ymax: ymax=tile.y
                
    max_square = 1
    max_square_x = 0
    max_square_y = 0

    def is_square(x, y, m):
        if x+m > xmax or y+m > ymax: return False
        for dx in range(m):
            for dy in range(m):
                uid = "{}_{}".format(x+dx, y+dy)
                if uid in not_found_tiles : return False
        return True

    ### Trouver le carré le plus grand
    for x in range(xmin, xmax+1):
        for y in range(ymin, ymax+1):
            while True:
                if is_square(x, y, max_square+1):
                    max_square_x = x
                    max_square_y = y
                    max_square = max_square + 1
                else:
                    break # while break
                    
    max_square_coord = ( coordFromTile(max_square_x, max_square_y) , coordFromTile(max_square_x+max_square, max_square_y+max_square) )
    print("Max square:{} at {},{}".format(max_square, max_square_x, max_square_y))
    return {"tiles": not_found_tiles, "max": max_square, "coord": max_square_coord}


class RouteServer(object):
    def __init__(self):
        self.stored_tiles = {}
        self.router = None
        self.myRouter = False
        self.mode = None
        self.thread = None

    def startRoute(self, mode, startLoc, endLoc, tiles, thread=True):
        print(tiles)
            
        if thread and self.myRouter and not self.myRouter.isComplete:
            print("Abord previous route...")
            self.myRouter.abort()
            self.thread.join()
            print("   ...OK")
        if mode != self.mode:
            self.mode = mode
            self.stored_tiles = {}
            self.router = Datastore(mode, cache_dir=os.path.join(Path.home(), '.tilescache'))
        coordDict = CoordDict(self.router)
        startPoint = coordDict.get(*startLoc)
        endPoint = coordDict.get(*endLoc)
        selectedTiles = []
        for t in tiles:
            if t not in self.stored_tiles:
                self.stored_tiles[t] = Tile(t)
            selectedTiles.append(self.stored_tiles[t])
            self.stored_tiles[t].getEntryPoints(self.router)
            if not self.stored_tiles[t].entryNodeId:
                return False, "No entry point for tiles", [t]

        self.myRouter = MyRouter(self.router, startPoint, endPoint, selectedTiles)
        if thread:
            self.thread = threading.Thread(target=self.myRouter.run)
            #Background thread will finish with the main program
            self.thread.setDaemon(True)
            #Start YourLedRoutine() in a separate thread
            self.thread.start()

        else:
            self.myRouter.run()

        return self.myRouter, self.isComplete, self.route

    @property
    def progress(self):
        return self.myRouter.progress
        
    @property
    def route(self):
        return self.myRouter.min_route
    
    @property
    def isComplete(self):
        return self.myRouter.isComplete
    

if __name__ == '__main__':
    #import time
    TilesToKml(['8251_5613', '8251_5614', '8249_5615'], "debug/test.kml", "test")
    #rs = RouteServer()
    #print(computeMissingKml(open("missing_tiles.kml", "rb")))
    # print(rs.startRoute([49.250775603162886,1.4452171325683596], [49.250775603162886,1.4452171325683596], [205], thread=False).min_route.getCoords(rs.myRouter.router))
    #print(rs.startRoute([49.250775603162886,1.4452171325683596], [49.250775603162886,1.4452171325683596], ["8257_5607", "8257_5610"], thread=False).min_route.routeLatLons)
    #pprint(minDists)
    # #print(rs.startRoute([49.250775603162886,1.4452171325683596], [49.250775603162886,1.4452171325683596], [205,206], thread=False).min_route.getCoords(rs.myRouter.router))
    # print(rs.startRoute([49.250775603162886,1.4452171325683596], [49.250775603162886,1.4452171325683596], [-1], thread=False).min_route.getCoords(rs.myRouter.router))

    #start_time = time.time()
    #rs.startRoute([49.01467940545091,1.389772879538316], [49.00386989926282,1.3952660758713222], [546,580], thread=False)
    #compute_time = time.time()-start_time
    #print("compute time:", compute_time)
    # start_time = time.time()
    # print(rs.startRoute([49.01467940545091,1.389772879538316], [49.00386989926282,1.3952660758713222], [546,580], thread=False).min_route.getCoords(rs.myRouter.router))
    # compute_time = time.time()-start_time
    # print("compute time:", compute_time)


    # myRouter = rs.startRoute([49.01467940545091,1.389772879538316], [49.00386989926282,1.3952660758713222], [546,580], thread=True)
    # while not myRouter.isComplete:
        # pass
    # print(myRouter.min_route.getCoords(rs.myRouter.router))

