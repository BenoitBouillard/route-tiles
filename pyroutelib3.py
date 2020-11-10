#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Loading OSM data and doing routing with it
# node_lat, node_lon = Router().data.rnodes[node_id][0], Router().data.rnodes[node_id][1]
# ----------------------------------------------------------------------------
# Copyright 2007, Oliver White
# Modifications: Copyright 2017-2019, Mikolaj Kuranowski -
# Based on https://github.com/gaulinmp/pyroutelib2
# ----------------------------------------------------------------------------
# This file is part of pyroutelib3.
#
# pyroutelib3 is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyroutelib3 is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyroutelib3. If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------------
# Changelog:
#  2007-11-04  OJW  Modified from pyroute.py
#  2007-11-05  OJW  Multiple forms of transport
#  2017-09-24  MK   Code cleanup
#  2017-09-30  MK   LocalFile - Only router
#  2017-10-11  MK   Access keys
#  2018-01-07  MK   Oneway:<Transport> tags & New distance function
#  2018-08-14  MK   Turn restrictions
#  2018-08-18  MK   New data download function
#  2019-09-15  MK   Allow for custom storage classes, instead of default dict
# ----------------------------------------------------------------------------
import math
import os
import time
import xml.etree.ElementTree as etree
from urllib.request import urlretrieve

from utils import distance, retry

__title__ = "pyroutelib3"
__description__ = "Library for simple routing on OSM data"
__url__ = "https://github.com/MKuranowski/pyroutelib3"
__author__ = "Oliver White"
__copyright__ = "Copyright 2007, Oliver White; Modifications: Copyright 2017-2019, Mikolaj Kuranowski"
__credits__ = ["Oliver White", "Mikolaj Kuranowski"]
__license__ = "GPL v3"
__version__ = "1.4"
__maintainer__ = "Mikolaj Kuranowski"
__email__ = "mkuranowski@gmail.com"


def weight_primary_roadcycle(t):
    w = int(t.get("maxspeed", "80"))
    if w <= 50:
        return 1
    if w <= 70:
        return 0.75
    if w <= 80:
        return 0.5
    return 0.25

def weight_primary_foot(t):
    w = int(t.get("maxspeed", "80"))
    if w>=90:
        return 0
    if w <= 50:
        return 1
    if w <= 70:
        return 0.75
    if w <= 80:
        return 0.5
    return 0.25


def filter_asphalt(t):
    # Allow asphalt path and zebra crossing
    if t.get("surface") in ['asphalt']:
        return 1
    if t.get("footway") in ['crossing']:
        return 1
    if t.get("crossing") in ['zebra']:
        return 1
    return 0


TYPES = {
    "car": {
        "weights": {"motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
                    "unclassified": 1, "residential": 0.7, "track": 0.5, "service": 0.5},
        "access": ["access", "vehicle", "motor_vehicle", "motorcar"]},
    "bus": {
        "weights": {"motorway": 10, "trunk": 10, "primary": 2, "secondary": 1.5, "tertiary": 1,
                    "unclassified": 1, "residential": 0.8, "track": 0.3, "service": 0.9},
        "access": ["access", "vehicle", "motor_vehicle", "psv", "bus"]},
    "roadcycle": {
        "weights": {"primary": weight_primary_roadcycle, "secondary": 1, "tertiary": 1,
                    "unclassified": 0.9, "residential": 0.9, "living_street": 0.9, "cycleway": 0.9,
                    "footway": filter_asphalt, "path": filter_asphalt},
        "access": ["access", "vehicle", "bicycle"]},
    "cycle": {
        "weights": {"trunk": 0.05, "primary": weight_primary_roadcycle, "secondary": 0.9, "tertiary": 1,
                    "unclassified": 1, "cycleway": 2, "residential": 2.5, "living_street": 2, "track": 1,
                    "service": 1, "bridleway": 0.8, "footway": 0.8, "steps": 0.5, "path": 1},
        "access": ["access", "vehicle", "bicycle"]},
    "horse": {
        "weights": {"primary": 0.05, "secondary": 0.15, "tertiary": 0.3, "unclassified": 1,
                    "residential": 1, "track": 1.5, "service": 1, "bridleway": 5, "path": 1.5},
        "access": ["access", "horse"]},
    "footroad": {
        "mode": "foot",
        "weights": {"trunk": 0.0, "primary": 0.6, "secondary": 0.9, "tertiary": 1,
                    "unclassified": 1, "residential": 1, "living_street": 1, "track": 0, "service": 1,
                    "bridleway": 1, "footway": 1, "path": 0, "steps": 1},
        "access": ["access", "foot"],
        "reverse_way":True},
    "foot": {
        "weights": {"trunk": 0.3, "primary": weight_primary_foot, "secondary": 0.9, "tertiary": 1,
                    "unclassified": 1, "residential": 1, "living_street": 1, "track": 1, "service": 1,
                    "bridleway": 1, "footway": 1, "path": 1, "steps": 1},
        "access": ["access", "foot"],
    "reverse_way":True},
    "trail": {
        "weights": {"trunk": 0.1, "primary": 0.3, "secondary": 0.6, "tertiary": 0.7,
                    "unclassified": 0.7, "residential": 0.8, "living_street": 0.8, "track": 0.9, "service": 0.8,
                    "bridleway": 0.9, "footway": 0.9, "path": 1, "steps": 1},
        "access": ["access", "foot"],
        "reverse_way":True},
    "tram": {
        "weights": {"tram": 1, "light_rail": 1},
        "access": ["access"]},
    "train": {
        "weights": {"rail": 1, "light_rail": 1, "subway": 1, "narrow_guage": 1},
        "access": ["access"]}
}

ZOOM_LEVEL = 15


def _which_tile(lat, lon, zoom):
    """Determine in which tile the given lat, lon lays"""
    n = 2 ** zoom
    x = n * ((lon + 180) / 360)
    y = n * ((1 - math.log(math.tan(math.radians(lat)) + (1 / math.cos(math.radians(lat)))) / math.pi) / 2)
    return int(x), int(y), int(zoom)


def _tile_boundary(x, y, z):
    """Return (left, bottom, right, top) of bbox of given tile"""
    n = 2 ** z

    def merc_to_lat(v):
        return math.degrees(math.atan(math.sinh(v)))

    top = merc_to_lat(math.pi * (1 - 2 * (y * (1 / n))))
    bottom = merc_to_lat(math.pi * (1 - 2 * ((y + 1) * (1 / n))))
    left = x * (360 / n) - 180
    right = left + (360 / n)
    return left, bottom, right, top


@retry(Exception, tries=6, delay=30, backoff=2)
def myurlretrieve(url, filename=None, reporthook=None, data=None):
    return urlretrieve(url, filename, reporthook, data)


def attributes(element):
    """Get OSM element attributes and do some common type conversion"""
    result = {}
    for k, v in element.attrib.items():
        if k == "uid":
            v = int(v)
        elif k == "changeset":
            v = int(v)
        elif k == "version":
            v = float(v)
        elif k == "id":
            v = int(v)
        elif k == "lat":
            v = float(v)
        elif k == "lon":
            v = float(v)
        elif k == "open":
            v = (v == "true")
        elif k == "visible":
            v = (v == "true")
        elif k == "ref":
            v = int(v)
        elif k == "comments_count":
            v = int(v)
        result[k] = v
    return result


def equivalent(tag):
    """Simplifies a bunch of tags to nearly-equivalent_way ones"""
    equivalent_way = {
        "motorway_link": "motorway",
        "trunk_link": "trunk",
        "primary_link": "primary",
        "secondary_link": "secondary",
        "tertiary_link": "tertiary",
        "minor": "unclassified",
        "pedestrian": "footway",
        "platform": "footway",
    }
    return equivalent_way.get(tag, tag)


class Datastore:
    """Object for storing routing data with basic OSM parsing functionality"""

    def __init__(self, transport, localfile=False, expire_data=30, storage_class=dict, cache_dir="tilescache"):
        """Initialise an OSM-file parser"""
        # Routing data
        print("############ DATASTORE init ################")
        self.routing = storage_class()
        self.routing_reverse = storage_class()
        self.not_update_routing = storage_class()
        self.rnodes = storage_class()
        self.mandatoryMoves = storage_class()
        self.forbiddenMoves = storage_class()
        self.cache_dir = cache_dir

        # Info about OSM
        self.tiles = storage_class()
        self.expire_data = 86400 * expire_data  # expire_data is in days, we preform calculations in seconds
        self.localFile = bool(localfile)

        # Parsing/Storage data
        self.storage_class = storage_class

        # Dict-type custom transport weights
        if isinstance(transport, dict):
            # Check if required info is in given transport dict
            assert {"name", "access", "weights"}.issubset(transport.keys())
            self.transport = transport["name"]
            self.type = transport

        else:
            self.transport = transport if transport not in ["cycle",
                                                            "roadcycle"] else "bicycle"  # Osm uses bicycle in tags
            self.type = TYPES[transport].copy()
            if 'mode' in self.type:
                self.transport = self.type['mode']

        # Load local file if it was passed
        if self.localFile:
            self.load_osm(localfile)

    def clean(self):
        self.routing = self.storage_class()
        self.routing_reverse = self.storage_class()

        # Info about OSM
        self.tiles = self.storage_class()

    def _allowed_vehicle(self, tags):
        """Check way against access tags"""

        # Default to true
        allowed = True

        # Priority is ascending in the access array
        for key in self.type["access"]:
            if key in tags:
                if tags[key] in ["no", "private"]:
                    allowed = False
                else:
                    allowed = True

        return allowed

    def node_lat_lon(self, node):
        """Get node's lat lon"""
        return self.rnodes[node]

    def get_area(self, lat, lon):
        """Download data in the vicinity of a lat/long"""
        # Don't download data if we loaded a custom OSM file
        if self.localFile:
            return

        # Get info on tile in wich lat, lon lays
        x, y, z = _which_tile(lat, lon, ZOOM_LEVEL)

        self.get_tile(x, y, z)

    def get_area_rect(self, lat1, lon1, lat2, lon2):
        """Download data in the vicinity of a lat/long"""
        # Don't download data if we loaded a custom OSM file
        if self.localFile:
            return

        # Get info on tile in wich lat, lon lays
        x1, y1, z1 = _which_tile(lat1, lon1, ZOOM_LEVEL)
        x2, y2, z2 = _which_tile(lat2, lon2, ZOOM_LEVEL)
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.get_tile(x, y, z1)

    def get_tile(self, x, y, z):
        tile_id = "{0},{1}".format(x, y)

        # Don't redownload tiles
        if tile_id in self.tiles:
            return

        # Download tile data
        self.tiles[tile_id] = True
        directory = os.path.join(self.cache_dir, "{}".format(z), str(x), str(y))
        filename = os.path.join(directory, "data.osm")

        # Make sure directory to which we download .osm files exists
        if not os.path.exists(directory):
            os.makedirs(directory)

        # In versions prior to 1.0 tiles were saved to tilescache/z/x/y/data.osm.pkl
        elif os.path.exists(filename + ".pkl"):
            os.rename(filename + ".pkl", filename)

        # Don't redownload data from pre-expire date
        try:
            downloaded_seconds_ago = time.time() - os.path.getmtime(filename)
        except OSError:
            downloaded_seconds_ago = math.inf

        if downloaded_seconds_ago >= self.expire_data:
            left, bottom, right, top = _tile_boundary(x, y, z)
            myurlretrieve(
                "https://api.openstreetmap.org/api/0.6/map?bbox={0},{1},{2},{3}".format(left, bottom, right, top),
                filename)
        try:
            self.load_osm(filename)
        except etree.ParseError:
            left, bottom, right, top = _tile_boundary(x, y, ZOOM_LEVEL)
            myurlretrieve(
                "https://api.openstreetmap.org/api/0.6/map?bbox={0},{1},{2},{3}".format(left, bottom, right, top),
                filename)
            self.load_osm(filename)

    def parse_osm_file(self, file):
        """Return nodes, ways and realations of given file
           Only highway=* and railway=* ways are returned, and
           only type=restriction (and type=restriction:<transport type>) are returned"""
        nodes = self.storage_class()
        ways = self.storage_class()
        relations = self.storage_class()

        # Check if a file-like object was passed
        if hasattr(file, "read"):
            fp = file

        # If not assume that "file" is a path to file
        else:
            fp = open(os.fspath(file), "r", encoding="utf-8")

        try:
            for event, elem in etree.iterparse(fp):
                data = attributes(elem)
                data["tag"] = {i.attrib["k"]: i.attrib["v"] for i in elem.iter("tag")}

                if elem.tag == "node":
                    nodes[data["id"]] = data

                # Store only potentially routable ways
                elif elem.tag == "way" and (data["tag"].get("highway") or data["tag"].get("railway")):
                    data["nd"] = [int(i.attrib["ref"]) for i in elem.iter("nd")]
                    ways[data["id"]] = data

                # Store only potential turn restrictions
                elif elem.tag == "relation" and data["tag"].get("type", "").startswith("restriction"):
                    data["member"] = [attributes(i) for i in elem.iter("member")]
                    relations[data["id"]] = data

        finally:
            # Close file if a path was passed
            if not hasattr(file, "read"):
                fp.close()

        return nodes, ways, relations

    def load_osm(self, file):
        """Load data from OSM file to self"""
        nodes, ways, relations = self.parse_osm_file(file)

        for wayId, wayData in ways.items():
            way_nodes = []
            for nd in wayData["nd"]:
                if nd not in nodes:
                    continue
                way_nodes.append((nodes[nd]["id"], nodes[nd]["lat"], nodes[nd]["lon"]))
            self.store_way(wayData["tag"], way_nodes)

        for relId, relData in relations.items():
            try:
                # Ignore reltions which are not restrictions
                if relData["tag"].get("type") not in ("restriction", "restriction:" + self.transport):
                    continue

                # Ignore restriction if except tag points to any "access" values
                if set(relData["tag"].get("except", "").split(";")).intersection(self.type["access"]):
                    continue

                # Ignore foot restrictions unless explicitly stated
                if self.transport == "foot" and relData["tag"].get("type") != "restriction:foot" and \
                        "restriction:foot" not in relData["tag"]:
                    continue

                restriction_type = relData["tag"].get("restriction:" + self.transport) or relData["tag"]["restriction"]

                nodes = []
                from_member = [i for i in relData["member"] if i["role"] == "from"][0]
                to_member = [i for i in relData["member"] if i["role"] == "to"][0]

                for via_member in [i for i in relData["member"] if i["role"] == "via"]:
                    if via_member["type"] == "way":
                        nodes.append(ways[int(via_member["ref"])]["nd"])
                    else:
                        nodes.append([int(via_member["ref"])])

                nodes.insert(0, ways[int(from_member["ref"])]["nd"])
                nodes.append(ways[int(to_member["ref"])]["nd"])

                self.store_restriction(restriction_type, nodes)

            except (KeyError, AssertionError, IndexError):
                continue

    def store_restriction(self, restriction_type, members):
        # Order members of restriction, so that members look somewhat like this:
        # ([a, b], [b, c], [c], [c, d, e], [e, f])
        for x in range(len(members) - 1):
            common_node = (set(members[x]).intersection(set(members[x + 1]))).pop()

            # If first node of member[x+1] is different then common_node, try to reverse it
            if members[x + 1][0] != common_node:
                members[x + 1].reverse()

            # Only the "from" way can be reversed while ordering the nodes,
            # Otherwise, the x way could be reversed twice (as member[x] and member[x+1])
            if x == 0 and members[x][-1] != common_node:
                members[x].reverse()

            # Assume member[x] and member[x+1] are ordered correctly
            assert members[x][-1] == members[x + 1][0]

        if restriction_type.startswith("no_"):
            # Start by denoting 'from>via'
            forbid = "{},{},".format(members[0][-2], members[1][0])

            # Add all via members
            for x in range(1, len(members) - 1):
                for i in members[x][1:]:
                    forbid += "{},".format(i)

            # Finalize by denoting 'via>to'
            forbid += str(members[-1][1])

            self.forbiddenMoves[forbid] = True

        elif restriction_type.startswith("only_"):
            force = []
            force_activator = "{},{}".format(members[0][-2], members[1][0])

            # Add all via members
            for x in range(1, len(members) - 1):
                for i in members[x][1:]:
                    force.append(i)

            # Finalize by denoting 'via>to'
            force.append(members[-1][1])

            self.mandatoryMoves[force_activator] = force

    def store_way(self, tags, nodes):
        highway = equivalent(tags.get("highway", ""))
        railway = equivalent(tags.get("railway", ""))
        oneway = tags.get("oneway", "")

        # Oneway is default on roundabouts
        if not oneway and (tags.get("junction", "") in ["roundabout", "circular"] or highway == "motorway"):
            oneway = "yes"

        if self.type.get("reverse_way",False) or (
                oneway in ["yes", "true", "1", "-1"] and tags.get("oneway:" + self.transport, "yes") == "no"):
            oneway = "no"

        # Calculate what vehicles can use this route
        weight = self.type["weights"].get(highway, 0) or self.type["weights"].get(railway, 0)

        if callable(weight):
            weight = weight(tags)

        # Check against access tags
        if (not self._allowed_vehicle(tags)) or weight <= 0:
            return

        # Store routing information
        for index in range(1, len(nodes)):
            node1_id, node1_lat, node1_lon = nodes[index - 1]
            node2_id, node2_lat, node2_lon = nodes[index]

            # Check if nodes' positions are stored
            if node1_id not in self.rnodes:
                self.rnodes[node1_id] = (node1_lat, node1_lon)
            if node2_id not in self.rnodes:
                self.rnodes[node2_id] = (node2_lat, node2_lon)

            # Check if nodes have dicts for storing travel costs
            if node1_id not in self.routing:
                self.routing[node1_id] = {}
            if node2_id not in self.routing:
                self.routing[node2_id] = {}
            if node1_id not in self.routing_reverse:
                self.routing_reverse[node1_id] = {}
            if node2_id not in self.routing_reverse:
                self.routing_reverse[node2_id] = {}

            # Is way traversible forward?
            if oneway not in ["-1", "reverse"]:
                if node1_id not in self.not_update_routing or node2_id not in self.not_update_routing[node1_id]:
                    self.routing[node1_id][node2_id] = weight
                    self.routing_reverse[node2_id][node1_id] = weight

            # Is way traversible backword?
            if oneway not in ["yes", "true", "1"]:
                if node2_id not in self.not_update_routing or node1_id not in self.not_update_routing[node2_id]:
                    self.routing[node2_id][node1_id] = weight
                    self.routing_reverse[node1_id][node2_id] = weight

    def find_node(self, lat, lon):
        """Find the nearest node that can be the start of a route"""
        # Get area around location we're trying to find
        self.get_area(lat, lon)
        max_dist, closest_node = math.inf, None

        # Iterate over nodes and overwrite closest_node if it's closer
        for node_id, node_pos in self.rnodes.items():

            distance_diff = distance(node_pos, (lat, lon))
            if distance_diff < max_dist:
                max_dist = distance_diff
                closest_node = node_id

        return closest_node

    def report(self):
        """Display some info about the loaded data"""
        print("Loaded %d nodes" % len(list(self.rnodes)))
        print("Loaded %d %s routes" % (len(list(self.routing)), self.transport))
