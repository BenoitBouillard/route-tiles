import http.server
import socketserver
from urllib import parse
from functools import partial
import os
import io
import re
from routeServer import RouteServer, computeMissingKml, LatLonsToGpx, TilesToKml
import json
import zlib
import struct
from datetime import datetime
import random
import string
from pprint import pprint
from pathlib import Path


# TODO [Improvement] Add CANCEL to merge
# TODO [Improvement] Add Elevation
# TODO [Improvement] Add option to avoid turn around (Turn around price ?)
# TODO [Improvement] Direct download trace
# TODO [Improvement] Add description to buttons
# TODO [Improvement] Add line command arguments for port
# TODO [Improvement] Add installation for python package


PORT = 8000

sessionDict = {}
chars = string.ascii_letters + string.digits

class SessionElement(object):
    """Arbitrary objects, referenced by the session id"""
    def __init__(self):
        self.routeServer = RouteServer()
    
def generateRandom(length):
    """Return a random string of specified length (used for session id's)"""
    return ''.join([random.choice(chars) for i in range(length)])

class RouteHttpServer(http.server.SimpleHTTPRequestHandler):
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = None
        self.sessionId = None
        # Create gpx folder is not exists for gpx export
        Path(os.path.join(self.directory, 'gpx')).mkdir(exist_ok=True)


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
        
    def do_GET_start_route(self):
        parsed_path = parse.urlparse(self.path)        
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        start = [float(qs['start[]'][0]), float(qs['start[]'][1])]
        end   = [float(qs['end[]'  ][0]), float(qs['end[]'  ][1])]
        mode   = qs['mode'][0]
        if 'tiles[]' in qs:
            tiles = qs['tiles[]']
            for i in range(len(tiles)):
                if '_' not in tiles[i]:
                    tiles[i] = int(tiles[i])
        else:
            tiles = []

        answer = {'sessionId':self.sessionId }

        router, message, info = self.session.routeServer.startRoute(mode, start, end, tiles)

        if router:
            answer['status'] = "OK"
            if self.session.routeServer.isComplete:
                answer['state'] = 'complete'
            else:
                answer['state'] = 'searching...'

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
        answer = { 'status':"OK" }  
        if self.session.routeServer.isComplete:
            answer['state'] = 'complete'
        else:
            answer['state'] = 'searching...'
            
        answer['progress'] = self.session.routeServer.progress
        route = self.session.routeServer.route
        if route:
            crc = "{:X}".format(zlib.crc32(struct.pack(">{}Q".format(len(route.route)), *route.route)))
            
            if 'findRouteId' not in qs or crc != qs['findRouteId'][0]:
                answer['findRouteId'] = crc
                answer['length'] = route.length
                answer['route'] = route.routeLatLons
            
        answer['sessionId'] = self.sessionId
        self.wfile.write(json.dumps(answer).encode('utf-8'))
    
    def do_GET_generate_gpx(self):
        parsed_path = parse.urlparse(self.path)        
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        
        gpxName = qs.get('name', [""])[0]
        if gpxName=="":
            gpxName = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        gpxFileName = gpxName
        if not gpxFileName.upper().endswith(".GPX"):
            gpxFileName += ".gpx"
        if "\\" in gpxFileName or "/" in gpxFileName:
            answer = { 'status':"Fail", 'message':"wrong filename" }  
        elif not self.session.routeServer.myRouter:
            answer = { 'status':"Fail", 'message':"No route" }  
        elif self.session.routeServer.myRouter.generateGpx(os.path.join(self.directory, 'gpx', gpxFileName), gpxName):
            answer = { 'status':"OK", 'path':'gpx/'+gpxFileName }  
        else:
            answer = { 'status':"Fail", 'message':"error generating GPX" }  
        answer['sessionId'] = self.sessionId
        self.wfile.write(json.dumps(answer).encode('utf-8'))
       
    def do_GET_generate_kml_tiles(self):
        parsed_path = parse.urlparse(self.path)        
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        
        fileName = qs.get('name', [""])[0]
        if 'tiles[]' in qs:
            tiles = qs['tiles[]']
            for i in range(len(tiles)):
                if '_' not in tiles[i]:
                    tiles[i] = int(tiles[i])
        else:
            tiles = []
        
        if fileName=="":
            fileName = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        kmlFileName = fileName
        if not kmlFileName.upper().endswith(".KML"):
            kmlFileName += ".kml"
        if "\\" in kmlFileName or "/" in kmlFileName:
            answer = { 'status':"Fail", 'message':"wrong filename" }  
        elif TilesToKml(tiles, os.path.join(self.directory, 'gpx', kmlFileName), fileName):
            answer = { 'status':"OK", 'path':'gpx/'+kmlFileName }  
        else:
            answer = { 'status':"Fail", 'message':"error generating KML" }  
        self.wfile.write(json.dumps(answer).encode('utf-8'))
    
        
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
    def do_GET(self):
        parsed_path = parse.urlparse(self.path)
        self.session = self.Session()

        mname = 'do_GET_' + parsed_path.path[1:]
        if hasattr(self, mname):
            self._set_headers()
            method = getattr(self, mname)
            method()
        else:
            super().do_GET()
            
    def do_POST(self):
        parsed_path = parse.urlparse(self.path)
        self.session = self.Session()

        if parsed_path.path=="/set_kml":
            self._set_headers()
            r, info = self.deal_post_data()
            if r:
                tiles = computeMissingKml(r)
                if tiles:
                    self.wfile.write(json.dumps({'status': 'OK', 'sessionId': self.sessionId, 'tiles':tiles['tiles'], 'maxSquare':tiles['coord']}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({'status': 'Fail', 'message': 'unable to read the KML file'}).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({'status': 'Fail', 'message': 'unable to decode data'}).encode('utf-8'))
                
        if parsed_path.path=="/generate_gpx":
            self._set_headers()
            pprint(dict(self.headers))
            length = int(self.headers['Content-Length'])
            data = self.rfile.read(length).decode("utf-8")
            qs = parse.parse_qs(data, keep_blank_values=True)
            gpxName = str(qs.get('name', [""])[0])
            latlons = [x.split(',') for x in qs['points[]']]
            print(latlons)
            if gpxName=="":
                gpxName = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
            gpxFileName = gpxName
            if not gpxFileName.upper().endswith(".GPX"):
                gpxFileName += ".gpx"
            if "\\" in gpxFileName or "/" in gpxFileName:
                answer = { 'status':"Fail", 'message':"wrong filename" }  
            elif not latlons:
                answer = { 'status':"Fail", 'message':"No route" }  
            elif LatLonsToGpx(latlons, os.path.join(self.directory, 'gpx', gpxFileName), gpxName):
                answer = { 'status':"OK", 'path':'gpx/'+gpxFileName }  
            else:
                answer = { 'status':"Fail", 'message':"error generating GPX" }  
            self.wfile.write(json.dumps(answer).encode('utf-8'))

                

    def deal_post_data(self):
        content_type = self.headers['content-type']
        if not content_type:
            return None, "Content-Type header doesn't contain boundary"
        boundary = content_type.split("=")[1].encode()
        remainbytes = int(self.headers['content-length'])
        line = self.rfile.readline()
        remainbytes -= len(line)
        if not boundary in line:
            return (None, "Content NOT begin with boundary ")
        line = self.rfile.readline()
        remainbytes -= len(line)
        fn = re.findall(r'Content-Disposition.*name="file"; filename="(.*)"', line.decode())
        if not fn:
            return (None, "Can't find out file name...")
        path = self.translate_path(self.path)
        fn = os.path.join(path, fn[0])
        line = self.rfile.readline()
        remainbytes -= len(line)
        line = self.rfile.readline()
        remainbytes -= len(line)
        out = io.BytesIO()
        preline = self.rfile.readline()
        remainbytes -= len(preline)
        while remainbytes > 0:
            line = self.rfile.readline()
            remainbytes -= len(line)
            if boundary in line:
                preline = preline[0:-1]
                if preline.endswith(b'\r'):
                    preline = preline[0:-1]
                out.write(preline)
                out.seek(0)
                return (out, "File '%s' upload success!" % fn)
            else:
                out.write(preline)
                preline = line
        return (None, "Unexpect Ends of data.")
        
    def Session(self, sessionId=None):
        parsed_path = parse.urlparse(self.path)        
        qs = parse.parse_qs(parsed_path.query, keep_blank_values=True)
        if "sessionId" in qs:
            self.sessionId=qs["sessionId"][0]
        else:
            self.sessionId=generateRandom(8)
        try:
            sessionObject = sessionDict[self.sessionId]
        except KeyError:
            self.sessionId=generateRandom(8)
            sessionObject = SessionElement()
            sessionDict[self.sessionId] = sessionObject
        return sessionObject     
        
handler_class = partial(RouteHttpServer, directory=os.path.join(os.path.dirname(__file__), 'static'))

with socketserver.TCPServer(("", PORT), handler_class) as httpd:
    print("serving at port", PORT)
    httpd.serve_forever()
    
    
    
