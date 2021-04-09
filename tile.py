from shapely.geometry import Point, LineString, LinearRing, Polygon
from fastkml import kml, styles

from utils import *


def coord_from_tile(x, y=None):
    n = 2 ** 14
    if y is None:
        s = x.split('_')
        x = int(s[0])
        y = int(s[1])
    lat = math.atan(math.sinh(math.pi * (1 - 2 * y / n))) * 180.0 / math.pi
    lon = x / n * 360.0 - 180.0
    return lat, lon


def geom_from_tile(x):
    s = x.split('_')
    x = int(s[0])
    y = int(s[1])
    return [list(coord_from_tile(x, y))[::-1], list(coord_from_tile(x + 1, y + 1))[::-1]]


def tile_from_coord(lat, lon, output="list"):
    n = 2 ** 14
    x = math.floor(n * (lon + 180) / 360)
    lat_r = lat * math.pi / 180
    y = math.floor(n * (1 - (math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi)) / 2)
    if output == "list":
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

    @property
    def edges(self):
        return [self.latlon]

    @property
    def entryNodeId(self):
        return [self]

    @property
    def entry_nodes_id(self):
        return [self.nodeId]


class CoordDict(object):
    def __init__(self, router):
        self.dict = {}
        self._router = router
        pass

    def get(self, lat, lon, node_id=None):
        name = "{}_{}".format(lat, lon)
        if name in self.dict:
            return self.dict[name]
        else:
            if node_id is None:
                node_id = self._router.find_node(lat, lon)
                # lat, lon = router.nodeLatLon(nodeId)
            coord = Coord(lat, lon, node_id)
            self.dict[name] = coord
            return coord


class ZoneWithEntries(object):
    def __init__(self, name=None):
        self.name = name
        self.entryNodeId = []
        self._entryNodesId = None

    @property
    def entry_nodes_id(self):
        if self._entryNodesId is None:
            self._entryNodesId = [n.nodeId for n in self.entryNodeId]
        return self._entryNodesId


class Tile(ZoneWithEntries):
    def __init__(self, uid, y=None):
        super().__init__(name='')
        if isinstance(uid, str):
            self.uid = uid
            s = uid.split("_")
            self.x = s[0]
            self.y = s[1]
        elif y is None:
            s = tile_from_coord((min([x[1] for x in uid]) + max([x[1] for x in uid])) / 2,
                                (max([x[0] for x in uid]) + min([x[0] for x in uid])) / 2)
            self.x = s[0]
            self.y = s[1]
            self.uid = "{0.x}_{0.y}".format(self)
        else:
            self.x = uid
            self.y = y
            self.uid = "{0.x}_{0.y}".format(self)

        geometry = geom_from_tile(self.uid)

        self.lonW = min([x[0] for x in geometry])
        self.lonE = max([x[0] for x in geometry])
        self.latS = min([x[1] for x in geometry])
        self.latN = max([x[1] for x in geometry])
        self.lon = (self.lonE + self.lonW) / 2
        self.lat = (self.latS + self.latN) / 2
        self.uid = "{0.x}_{0.y}".format(self)
        self.entryNodeId = []
        self.routesEntryNodes = {}
        self.polygon = Polygon([(self.lonW, self.latN), (self.lonW, self.latS), (self.lonE, self.latS),  (self.lonE, self.latN)])

    @property
    def middle(self):
        return self.lat, self.lon

    def __repr__(self):
        if self.name:
            return self.name
        return "Tile {}".format(self.name or self.uid)

    @property
    def edges(self):
        nw = (self.latN, self.lonW)
        ne = (self.latN, self.lonE)
        se = (self.latS, self.lonE)
        sw = (self.latS, self.lonW)
        return [nw, ne, se, sw]

    @property
    def segments(self):
        nw = (self.latN, self.lonW)
        ne = (self.latN, self.lonE)
        se = (self.latS, self.lonE)
        sw = (self.latS, self.lonW)
        return [(nw, ne), (ne, se), (se, sw), (sw, nw)]

    def linear_ring(self, offset=0):
        delta_lat = (self.latN - self.latS) / (1000 * distance((self.latN, self.lonW), (self.latS, self.lonW))) * offset
        delta_lon = (self.lonW - self.lonE) / (1000 * distance((self.latN, self.lonW), (self.latN, self.lonE))) * offset
        nw = (self.latN - delta_lat, self.lonW - delta_lon)
        ne = (self.latN - delta_lat, self.lonE + delta_lon)
        se = (self.latS + delta_lat, self.lonE + delta_lon)
        sw = (self.latS + delta_lat, self.lonW - delta_lon)
        return LinearRing([nw, ne, se, sw])

    @property
    def line_string_lon_lat(self):
        nw = (self.lonW, self.latN)
        ne = (self.lonE, self.latN)
        se = (self.lonE, self.latS)
        sw = (self.lonW, self.latS)
        return LineString([nw, ne, se, sw, nw])

    def to_dict(self):
        ne = (self.latN, self.lonE)
        sw = (self.latS, self.lonW)
        data = {'id': self.uid, 'bound': (sw, ne)}
        return data

    def get_entry_points(self, router):
        if self.entryNodeId:
            return
        router.get_area_rect(*self.edges[0], *self.edges[2])

        tile = self.linear_ring(offset=10)

        def add_entry_point(node):
            coord = Coord(*router.node_lat_lon(node), node)
            # if coord not in self.entryNodeId:
            if node not in [e.nodeId for e in self.entryNodeId]:
                self.entryNodeId.append(coord)

        new_points = []
        new_points_id = []

        for node_a, nodes in list(router.routing.items()):
            latlon = router.node_lat_lon(node_a)
            if distance(latlon, (self.lat, self.lon)) > 5:
                continue
            point_a = Point(*latlon)
            for node_b in list(nodes):
                point_b = Point(*router.node_lat_lon(node_b))
                line = LineString([point_a, point_b])
                if line.intersects(tile):
                    intersect_points = line.intersection(tile)
                    if intersect_points.geom_type == "Point":
                        intersect_points = [intersect_points]
                    elif intersect_points.geom_type == "Line":
                        intersect_points = [intersect_points.coords[0], intersect_points.coords[-1]]
                    else:
                        intersect_points = list(intersect_points)

                    intersect_points = list(intersect_points)

                    if point_a in intersect_points:
                        add_entry_point(node_a)
                        intersect_points.remove(point_a)
                    if point_b in intersect_points:
                        add_entry_point(node_b)
                        intersect_points.remove(point_b)

                    intersect_points.sort(key=lambda p: LineString([point_a, p]).length)

                    nodes_id = []
                    for point in intersect_points:
                        if point not in new_points:
                            node_id = int((str(self.uid) + str(len(new_points))).replace("_", ""))
                            router.rnodes[node_id] = (point.x, point.y)
                            new_points.append(point)
                            new_points_id.append(node_id)
                            add_entry_point(node_id)
                        else:
                            node_id = new_points_id[new_points.index(point)]
                        nodes_id.append(node_id)

                    for node_id in nodes_id:
                        if node_id not in router.routing:
                            router.routing[node_id] = {}

                    weight = router.routing[node_a][node_b]

                    if node_a not in router.not_update_routing:
                        router.not_update_routing[node_a] = []
                    router.not_update_routing[node_a].append(node_b)
                    n0 = node_a
                    for n in nodes_id:
                        router.routing[n0][n] = weight
                        router.routing[n][node_b] = weight
                        router.routing[n0].pop(node_b)
                        n0 = n

        print("Tile {} has {} entry nodes".format(self.name or self.uid, len(self.entryNodeId)))
        return


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