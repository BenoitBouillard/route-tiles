import http.server
import io
import json
import os
import random
import re
import socketserver
import string
import struct
import zlib
import argparse
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from pprint import pprint
from urllib import parse

from tilesrouter import RouteServer, latlons_to_gpx, tiles_to_kml
from statshunters import get_statshunters_activities, tiles_from_activities, compute_max_square, compute_cluster


PORT = 8000

sessionDict = {}
chars = string.ascii_letters + string.digits


class SessionElement(object):
    """Arbitrary objects, referenced by the session id"""

    def __init__(self):
        self.routeServer = RouteServer()
        self.last_access = datetime.now()

    def refresh(self):
        self.last_access = datetime.now()


def check_sessions():
    for session_id in list(sessionDict):
        session = sessionDict[session_id]
        if session.routeServer.is_complete:
            timeout = timedelta(0, 10*60) # 10min
        else:
            timeout = timedelta(0, 10*60) # 10min

        if datetime.now() - session.last_access > timeout:
            print("Remove session ", session_id)
            if not session.routeServer.is_complete:
                print("  abort previous routing")
                session.routeServer.myRouter.abort()
            sessionDict.pop(session_id)



def generate_random(length):
    """Return a random string of specified length (used for session id's)"""
    return ''.join([random.choice(chars) for _ in range(length)])


class RouteHttpServer(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.sessionId = None

    def do_GET_request(self):
        parsed_path = parse.urlparse(self.path)
        message_parts = [
            'CLIENT VALUES:',
            'client_address={} ({})'.format(
                self.client_address,
                self.address_string()),
            'command={}'.format(self.command),
            'path={}'.format(self.path),
            'real path={}'.format(parsed_path.path),
            'query={}'.format(parsed_path.query),
            'request_version={}'.format(self.request_version),
            '',
            'SERVER VALUES:',
            'server_version={}'.format(self.server_version),
            'sys_version={}'.format(self.sys_version),
            'protocol_version={}'.format(self.protocol_version),
            '',
            'HEADERS RECEIVED:',
        ]
        for name, value in sorted(self.headers.items()):
            message_parts.append(
                '{}={}'.format(name, value.rstrip())
            )
        message_parts.append('')
        message = '\r\n'.join(message_parts)
        self.send_response(200)
        self.send_header('Content-Type',
                         'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(message.encode('utf-8'))

    def do_GET_statshunters(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        url = qs['url'][0]
        if 'filter' in qs:
            sh_filter = qs['filter'][0]
        else:
            sh_filter = None

        data_folder = Path(__file__).parent.joinpath('data')
        data_folder.mkdir(exist_ok=True)
        folder = get_statshunters_activities(url, data_folder)

        tiles = tiles_from_activities(folder, filter_str=sh_filter)

        kml_max_square = compute_max_square(tiles)

        kml_cluster = compute_cluster(tiles)



        self.wfile.write(json.dumps({'status': 'OK',
                                     'tiles': list(tiles),
                                     'maxSquare': kml_max_square,
                                     'cluster': kml_cluster}).encode('utf-8'))

    def do_GET_start_route(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        start = [float(qs['start[]'][0]), float(qs['start[]'][1])]
        end = [float(qs['end[]'][0]), float(qs['end[]'][1])]
        mode = qs['mode'][0]
        turnaround_cost = float(qs['turnaroundCost'][0])
        if 'tiles[]' in qs:
            tiles = qs['tiles[]']
            for i in range(len(tiles)):
                if '_' not in tiles[i]:
                    tiles[i] = int(tiles[i])
        else:
            tiles = []

        answer = {'sessionId': self.sessionId}

        router, message, info = self.session.routeServer.start_route(mode, start, end, tiles, config={'turnaround_cost':turnaround_cost})

        if router:
            answer['status'] = "OK"
            if self.session.routeServer.is_complete:
                answer['state'] = 'complete'
            else:
                answer['state'] = 'searching'

            route = self.session.routeServer.route
            if route:
                crc = "{:X}".format(zlib.crc32(struct.pack(">{}Q".format(len(route.route)), *route.route)))

                answer['findRouteId'] = crc
                answer['length'] = route.length
                answer['route'] = route.routeLatLons
        else:
            answer['status'] = "Fail"
            answer['message'] = message
            answer['tiles'] = info

        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def do_GET_route_status(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        answer = {'status': "OK"}

        if self.session.routeServer.myRouter.error_code==0:
            if self.session.routeServer.is_complete:
                answer['state'] = 'complete'
            else:
                answer['state'] = 'searching'
            answer['progress'] = self.session.routeServer.progress
            route = self.session.routeServer.route
            if route:
                crc = "{:X}".format(zlib.crc32(struct.pack(">{}Q".format(len(route.route)), *route.route)))

                if self.session.routeServer.is_complete or 'findRouteId' not in qs or crc != qs['findRouteId'][0]:
                    answer['findRouteId'] = crc
                    answer['length'] = route.length
                    answer['route'] = route.routeLatLons
        else:
            answer['status'] = 'Fail'
            answer['error_code'] = self.session.routeServer.myRouter.error_code
            answer['error_args'] =self.session.routeServer.myRouter.error_args


        answer['sessionId'] = self.sessionId
        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def do_GET_generate_gpx(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)

        gpx_name = qs.get('name', [""])[0]
        if gpx_name == "":
            gpx_name = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        gpx_file_name = gpx_name
        if not gpx_file_name.upper().endswith(".GPX"):
            gpx_file_name += ".gpx"
        if "\\" in gpx_file_name or "/" in gpx_file_name:
            answer = {'status': "Fail", 'message': "wrong filename"}
        elif not self.session.routeServer.myRouter:
            answer = {'status': "Fail", 'message': "No route"}
        elif self.session.routeServer.myRouter.generate_gpx(
                os.path.join(self.directory, 'gpx', gpx_file_name), gpx_name):
            answer = {'status': "OK", 'path': 'gpx/' + gpx_file_name}
        else:
            answer = {'status': "Fail", 'message': "error generating GPX"}
        answer['sessionId'] = self.sessionId
        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def do_GET_generate_kml_tiles(self):
        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)

        file_name = qs.get('name', [""])[0]
        if 'tiles[]' in qs:
            tiles = qs['tiles[]']
            for i in range(len(tiles)):
                if '_' not in tiles[i]:
                    tiles[i] = int(tiles[i])
        else:
            tiles = []

        if file_name == "":
            file_name = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        kml_file_name = file_name
        if not kml_file_name.upper().endswith(".KML"):
            kml_file_name += ".kml"
        if "\\" in kml_file_name or "/" in kml_file_name:
            answer = {'status': "Fail", 'message': "wrong filename"}
        elif tiles_to_kml(tiles, os.path.join(self.directory, 'gpx', kml_file_name), file_name):
            answer = {'status': "OK", 'path': 'gpx/' + kml_file_name}
        else:
            answer = {'status': "Fail", 'message': "error generating KML"}
        self.wfile.write(json.dumps(answer).encode('utf-8'))

    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def do_GET(self):
        print(self.path)
        parsed_path = parse.urlparse(self.path)

        get_action_name = 'do_GET_' + parsed_path.path[1:]
        if hasattr(self, get_action_name):
            self.session = self.get_session()
            self._set_headers()
            method = getattr(self, get_action_name)
            method()
        else:
            super().do_GET()

    def do_POST(self):
        print(self.path)
        parsed_path = parse.urlparse(self.path)
        self.session = self.get_session()

        if parsed_path.path == "/generate_gpx":
            self._set_headers()
            pprint(dict(self.headers))
            length = int(self.headers['Content-Length'])
            data = self.rfile.read(length).decode("utf-8")
            qs = parse.parse_qs(data, keep_blank_values=True)
            gpx_name = str(qs.get('name', [""])[0])
            coords = [x.split(',') for x in qs['points[]']]
            if gpx_name == "":
                gpx_name = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            gpx_file_name = gpx_name
            if not gpx_file_name.upper().endswith(".GPX"):
                gpx_file_name += ".gpx"
            if "\\" in gpx_file_name or "/" in gpx_file_name:
                answer = {'status': "Fail", 'message': "wrong filename"}
            elif not coords:
                answer = {'status': "Fail", 'message': "No route"}
            elif latlons_to_gpx(coords, os.path.join(self.directory, 'gpx', gpx_file_name), gpx_name):
                answer = {'status': "OK", 'path': 'gpx/' + gpx_file_name}
            else:
                answer = {'status': "Fail", 'message': "error generating GPX"}
            self.wfile.write(json.dumps(answer).encode('utf-8'))

    def deal_post_data(self):
        content_type = self.headers['content-type']
        if not content_type:
            return None, "Content-Type header doesn't contain boundary"
        boundary = content_type.split("=")[1].encode()
        remain_bytes = int(self.headers['content-length'])
        line = self.rfile.readline()
        remain_bytes -= len(line)
        if boundary not in line:
            return None, "Content NOT begin with boundary "
        line = self.rfile.readline()
        remain_bytes -= len(line)
        fn = re.findall(r'Content-Disposition.*name="file"; filename="(.*)"', line.decode())
        if not fn:
            return None, "Can't find out file name..."
        path = self.translate_path(self.path)
        fn = os.path.join(path, fn[0])
        line = self.rfile.readline()
        remain_bytes -= len(line)
        line = self.rfile.readline()
        remain_bytes -= len(line)
        out = io.BytesIO()
        pre_line = self.rfile.readline()
        remain_bytes -= len(pre_line)
        while remain_bytes > 0:
            line = self.rfile.readline()
            remain_bytes -= len(line)
            if boundary in line:
                pre_line = pre_line[0:-1]
                if pre_line.endswith(b'\r'):
                    pre_line = pre_line[0:-1]
                out.write(pre_line)
                out.seek(0)
                return out, "File '%s' upload success!" % fn
            else:
                out.write(pre_line)
                pre_line = line
        return None, "Unexpected ends of data."

    def get_session(self):

        parsed_path = parse.urlparse(self.path)
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        if "sessionId" in qs:
            self.sessionId = qs["sessionId"][0]
        else:
            self.sessionId = generate_random(8)
        try:
            session_object = sessionDict[self.sessionId]
        except KeyError:
            self.sessionId = generate_random(8)
            session_object = SessionElement()
            sessionDict[self.sessionId] = session_object
            print("Create session", self.sessionId)

        session_object.refresh()
        check_sessions()
        return session_object


def route_tiles_server(port):
    # Create gpx folder is not exists for gpx export
    Path(__file__).parent.joinpath('static', 'gpx').mkdir(exist_ok=True)
    Path(__file__).parent.joinpath('debug').mkdir(exist_ok=True)
    handler_class = partial(RouteHttpServer, directory=str(Path(__file__).parent.joinpath('static')))
    with socketserver.TCPServer(("", port), handler_class) as httpd:
        print("serving at port", port)
        httpd.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Route Tiles server')
    parser.add_argument('-p', '--port', dest="port", type=int, default=PORT, help="Server port")
    args = parser.parse_args()

    port = vars(args)['port']

    route_tiles_server(port)

