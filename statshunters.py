import argparse
import os
import json
from urllib.request import urlretrieve
from utils import retry
from pathlib import Path
from tile import Tile
import re
from shapely.ops import unary_union
from fastkml import kml


@retry(Exception, tries=6, delay=60, backoff=2)
def myurlretrieve(url, filename=None, reporthook=None, data=None):
    return urlretrieve(url, filename, reporthook, data)


def statshunters_path(sharelink_url, folder):
    index = sharelink_url.split('/')[-1]
    activities_path = Path(folder).joinpath(index)
    activities_path.mkdir(parents=True, exist_ok=True)
    return activities_path


def get_statshunters_activities(sharelink_url, folder, full=False):
    activities_path = statshunters_path(sharelink_url, folder)
    page = 1

    if not full:
        while activities_path.joinpath("activities_{}.json".format(page + 2)).exists():
            page += 1

    while True:
        filepath = activities_path.joinpath("activities_{}.json".format(page))
        url = sharelink_url + "/api/activities?page={0}".format(page)
        print("Get page {} ({})".format(page, url))
        myurlretrieve(url, filepath)
        with open(filepath) as f:
            d = json.load(f)
            if len(d['activities']) == 0:
                break
        page += 1

    return activities_path


def tiles_from_activities(activities_dir, filter_str=None):
    # Get tiles from activities files from statshunters
    directory = os.fsencode(activities_dir)
    tiles = []

    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        if filename.endswith(".json"):
            with open(os.path.join(activities_dir, filename)) as f:
                d = json.load(f)
                for activity in d['activities']:
                    if filter_str and not eval(filter_str, globals(),activity):
                        continue
                    for tile in activity['tiles']:
                        uid = "{0}_{1}".format(tile['x'], tile['y'])
                        if uid not in tiles:
                            tiles.append(uid)
    return frozenset(tiles)


def getKmlFromGeom(geom):
    # Create the root KML object
    k = kml.KML()
    ns = '{http://www.opengis.net/kml/2.2}'

    # Create a KML Document and add it to the KML root object
    d = kml.Document(ns)
    k.append(d)

    # Create a KML Folder and add it to the Document
    f = kml.Folder(ns)
    d.append(f)

    # Create a KML Folder and nest it in the first Folder
    nf = kml.Folder(ns)
    f.append(nf)

    # Create a second KML Folder within the Document
    f2 = kml.Folder(ns)
    d.append(f2)

    # Create a Placemark with a simple polygon geometry and add it to the
    # second folder of the Document
    p = kml.Placemark(ns)
    p.geometry =  geom
    f2.append(p)

    return k.to_string()


def compute_zones(tiles):
    tiles = set(tiles)
    clusters = []
    while True:
        if len(tiles) == 0:
            break

        for c in tiles:
            cluster = set([c])
            boundary = set([c])
            break

        tiles -= cluster

        while True:
            new_c = set()
            for tile in boundary:
                x, y = tile
                for dx, dy in adjoining:
                    if (x + dx, y + dy) in tiles:
                        new_c.add((x + dx, y + dy))
            if new_c:
                cluster |= new_c
                boundary = new_c
                tiles -= new_c
            else:
                break
        clusters.append(cluster)

    clusters.sort(key=len, reverse=True)
    return clusters


adjoining = [(1, 0), (-1, 0), (0, 1), (0, -1) ]


def compute_cluster(tiles):
    if isinstance(list(tiles)[0], str):
        tiles = set([tuple([int(i) for i in t.split('_')]) for t in tiles])
    cluster_tiles = set()
    for (x,y) in tiles:
        for dx, dy in adjoining:
            if (x + dx, y + dy) not in tiles:
                break
        else:
            cluster_tiles.add((x, y))

    if len(cluster_tiles)==0:
        return 0
    zones = compute_zones(cluster_tiles)

    geom_z = unary_union([Tile(*t).polygon for t in zones[0]])

    return getKmlFromGeom(geom_z)


def compute_max_square(tiles):

    def is_square(x, y, m):
        for dx in range(m):
            for dy in range(m):
                uid = "{}_{}".format(x+dx, y+dy)
                if uid not in tiles : return False
        return True

    max_square = 0
    x_max = 0
    y_max = 0
    for tile in tiles:
        x = int(tile.split('_')[0])
        y = int(tile.split('_')[1])
        while is_square(x, y, max_square+1):
            max_square += 1
            x_max = x
            y_max = y
    tiles = set()
    for x in range(x_max, x_max+max_square):
        for y in range(y_max, y_max+max_square):
            tiles.add(Tile("{}_{}".format(x,y)))
    geom_z = unary_union([t.polygon for t in tiles])
    return getKmlFromGeom(geom_z)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute exploration ratio of a zone')
    parser.add_argument('-s', '--sharelink', dest="sharelink", help="Stathunters share link to recover data")
    args = parser.parse_args()

    sharelink = vars(args)['sharelink']

    index = get_statshunters_activities(sharelink)

    tiles = tiles_from_activities(index)

    print(compute_max_square(tiles))
