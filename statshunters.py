import argparse
import os
import json
from urllib.request import urlretrieve
from utils import retry
from pathlib import Path
import re


@retry(Exception, tries=6, delay=60, backoff=2)
def myurlretrieve(url, filename=None, reporthook=None, data=None):
    return urlretrieve(url, filename, reporthook, data)


def get_statshunters_activities(sharelink_url, folder, full=False):
    index = sharelink_url.split('/')[-1]
    page = 1

    activities_path = Path(folder).joinpath(index)
    activities_path.mkdir(exist_ok=True)

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
                    if filter_str and not eval(filter_str, globals(),{"activity": activity}):
                        continue
                    for tile in activity['tiles']:
                        uid = "{0}_{1}".format(tile['x'], tile['y'])
                        if uid not in tiles:
                            tiles.append(uid)
    return frozenset(tiles)


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
    return max_square, x_max, y_max


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compute exploration ratio of a zone')
    parser.add_argument('-s', '--sharelink', dest="sharelink", help="Stathunters share link to recover data")
    args = parser.parse_args()

    sharelink = vars(args)['sharelink']

    index = get_statshunters_activities(sharelink)

    tiles = tiles_from_activities(index)

    print(compute_max_square(tiles))
