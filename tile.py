from mathutils import *
from shapely.geometry import Point, LineString, LinearRing
import math  
    
def coordFromTile(x, y=None):
    n = 2**14
    if y is None:
        s = x.split('_')
        x = int(s[0])
        y = int(s[1])
    lat = math.atan( math.sinh( math.pi * (1 - 2*y / n ) ) ) * 180.0 / math.pi
    lon = x / n * 360.0 - 180.0
    return lat, lon
    

def geomFromTile(x, y=None):
    if y is None:
        s = x.split('_')
        x = int(s[0])
        y = int(s[1])
    return [ list(coordFromTile(x, y))[::-1], list(coordFromTile(x+1, y+1))[::-1] ]


def TileFromCoord(lat, lon, output="list"):
    n = 2**14
    x = math.floor(n * (lon + 180 ) / 360)
    lat_r = lat*math.pi/180
    y = math.floor(n * ( 1 - ( math.log( math.tan(lat_r) + 1/math.cos(lat_r) ) / math.pi ) ) / 2)
    if output=="list":
        return x, y
    else:
        return "{}_{}".format(x, y)


class Coord(object):
    def __init__(self, lat, lon, node_id=None):
        self.lat = lat
        self.lon = lon
        self.nodeId = node_id
    @property
    def latlon(self):
        return self.lat, self.lon
    def __repr__(self):
        return "{},{}({})".format(self.lat, self.lon, self.nodeId)
        
class CoordDict(object):
    def __init__(self, router):
        self.dict = {}
        self._router = router
        pass
    def get(self, lat, lon, nodeId=None):
        name = "{}_{}".format(lat, lon)
        if name in self.dict:
            return self.dict[name]
        else:
            if nodeId is None:
                nodeId = self._router.findNode(lat, lon)
                # lat, lon = router.nodeLatLon(nodeId)
            coord = Coord(lat, lon, nodeId)
            self.dict[name] = coord
            return coord

class ZoneWithEntries(object):
    def __init__(self, name=None):
        self.name = name
        self.entryNodeId = []
        self._entryNodesId = None
        
 
    @property
    def entryNodesId(self):
        if self._entryNodesId is None:
            self._entryNodesId = [n.nodeId for n in self.entryNodeId]
        return self._entryNodesId
        
# class Point(ZoneWithEntries):
    # def __init__(self, name, coord):
        # super().__init__(name=name)
        # self.name = name
        # self.entryNodeId.append(coord)
    # @property
    # def coord(self):
        # return self.entryNodeId[0]
        
class Tile(ZoneWithEntries):
    def __init__(self, uid):
        super().__init__(name='')
        if isinstance(uid, str):
            self.uid = uid
            s = uid.split("_")
            self.x = s[0]
            self.y = s[1]
        else:
            s = TileFromCoord((min([x[1] for x in uid])+max([x[1] for x in uid]))/2, (max([x[0] for x in uid])+min([x[0] for x in uid]))/2)
            self.x = s[0]
            self.y = s[1]
            self.uid = "{0.x}_{0.y}".format(self)
            
        geometry = geomFromTile(self.uid)
        
        self.lonW = min([x[0] for x in geometry])
        self.lonE = max([x[0] for x in geometry])
        self.latS = min([x[1] for x in geometry])
        self.latN = max([x[1] for x in geometry])
        self.lon = (self.lonE+self.lonW)/2
        self.lat = (self.latS+self.latN)/2
        self.uid = "{0.x}_{0.y}".format(self)
        self.entryNodeId = []
        
        
    @property
    def middle(self):
        return self.lat, self.lon
        
    def __repr__(self):
        if self.name: return self.name
        return "Tile {}".format(self.name or self.uid)
        
    @property  
    def edges(self):
        nw = (self.latN, self.lonW)
        ne = (self.latN, self.lonE)
        se = (self.latS, self.lonE)
        sw = (self.latS, self.lonW)
        return [ nw, ne, se, sw ]
        
    @property  
    def segments(self):
        nw = (self.latN, self.lonW)
        ne = (self.latN, self.lonE)
        se = (self.latS, self.lonE)
        sw = (self.latS, self.lonW)
        return [ (nw, ne), (ne, se), (se, sw), (sw, nw) ]
        
    def linearRing(self, offset=0):
        deltaLat = (self.latN - self.latS) / (1000 * distance((self.latN, self.lonW), (self.latS, self.lonW))) * offset
        deltaLon = (self.lonW - self.lonE) / (1000 * distance((self.latN, self.lonW), (self.latN, self.lonE))) * offset
        nw = (self.latN - deltaLat, self.lonW - deltaLon)
        ne = (self.latN - deltaLat, self.lonE + deltaLon)
        se = (self.latS + deltaLat, self.lonE + deltaLon)
        sw = (self.latS + deltaLat, self.lonW - deltaLon)
        return LinearRing([ nw, ne, se, sw ])
        
    @property  
    def lineStringLonLat(self):
        nw = (self.lonW, self.latN)
        ne = (self.lonE, self.latN)
        se = (self.lonE, self.latS)
        sw = (self.lonW, self.latS)
        return LineString([ nw, ne, se, sw, nw ])
        
    def toDict(self):
        ne = (self.latN, self.lonE)
        sw = (self.latS, self.lonW)
        data = { 'id':self.uid, 'bound': (sw, ne) }
        return data
    
    def getEntryPoints(self, router):
        if self.entryNodeId: return
        router.getAreaRect(*self.edges[0], *self.edges[2])
        
        tile = self.linearRing(offset=10)
        
        def addEntryPoint(node):
            coord = Coord(*router.nodeLatLon(node), node)
            #if coord not in self.entryNodeId:
            if node not in [e.nodeId for e in self.entryNodeId]:
                self.entryNodeId.append(coord)
                
        newPoints = []
        newPointsId = []
        
        for nodeA, nodes in list(router.routing.items()):
            latlon = router.nodeLatLon(nodeA)
            if distance(latlon, (self.lat, self.lon)) > 5: continue
            pointA = Point(*latlon)
            for nodeB in list(nodes):
                pointB = Point(*router.nodeLatLon(nodeB))
                line = LineString([pointA, pointB])
                if line.intersects(tile):
                    intersectPoints = line.intersection(tile)
                    if intersectPoints.geom_type == "Point":
                        intersectPoints = [intersectPoints]
                    else:
                        intersectPoints = list(intersectPoints)
                    
                    intersectPoints = list(intersectPoints)
                    
                    if pointA in intersectPoints:
                       addEntryPoint(nodeA)
                       intersectPoints.remove(pointA)
                    if pointB in intersectPoints:
                       addEntryPoint(nodeB)
                       intersectPoints.remove(pointB)
                       
                    intersectPoints.sort(key=lambda p:LineString([pointA, p]).length)
                    
                    nodesId = []
                    for point in intersectPoints:
                        if point not in newPoints:
                            nodeId = int((str(self.uid) + str(len(newPoints))).replace("_",""))
                            router.rnodes[nodeId] = (point.x, point.y)
                            newPoints.append(point)
                            newPointsId.append(nodeId)
                            addEntryPoint(nodeId)
                        else:
                            nodeId = newPointsId[newPoints.index(point)]
                        nodesId.append(nodeId)
                    
                    for nodeId in nodesId:
                        if nodeId not in router.routing: router.routing[nodeId] = {}
                        
                    weight = router.routing[nodeA][nodeB]
                    
                    n0 = nodeA
                    for n in nodesId:
                        router.routing[n0][n] = weight
                        router.routing[n][nodeB] = weight
                        router.routing[n0].pop(nodeB)   
                        n0 = n
                        
        print("Tile {} has {} entry nodes".format(self.name or self.uid, len(self.entryNodeId)))
        return
                
    
