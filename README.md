# Route Tiles project

## Motivation

This project objective is to compute route to explore tiles, by cycling or running.
For "tiles" information, see https://www.statshunters.com or https://veloviewer.com.

## Installation guide

Requirements:

- python 3.x


Open a terminal window and na`vigate to the folder that you want
to download route-tiles into.
Write in the terminal window

``` shell
git clone https://github.com/BenoitBouillard/route-tiles.git
```

followed by 

``` shell
cd route-tiles
```

and at last to install python package

``` shell
pip install -r requirements.txt
```

## User manual

There are 2 parts:
- the server
- the user interface

### Server

#### Server role
The server receive requests from the user interface and compute the route by:
- create http server for user interface
- download OpenStreetMap tiles
- find the nearest point of start/stop point
- find all the entry points of selected tiles
- compute route from start to end point passing by selected tiles

#### running the server

The server is a python script. To launch it, 
run this command in a terminal from the installation folder:

``` shell
python route-tile-server.py
```

A message should be displayed:

``` shell
serving at port 8000
```


### User interface

Once the server is running, it is possible to use the user interface.
It is a web page. On the same computer than the server, 
it is accessible with url http://localhost:8000

To find a route, several information are mandatory or possible:
- displacement mode
- start/end position
- tiles to visit

When there is enough information, a route request will be send to the server
after a few seconds.

The status of the routing is displayed:
- "wait..." Wait a few seconds before sending the request to the server
- "ask for route..." The request has been send and waiting for the answer
- "searching..." Route searching in progress. The map will display its current optimal route
- "complete" Optimal route has been find

Data are stored locally by the browser. If you refresh the page 
(or close and open it later), latest data will be recovered.

#### Displacement mode

It is possible to choose from several modes:
- **Route**: it will use only asphalt: road, cycle path if asphalt. 
             Avoid major road
- **Chemin**: use any path
- **Trail**: use path preferably

#### start and end position

Start position is mandatory. End position is optional. 
If there is no end position, the route will be a loop 
(return to the start point).

To define the start or end position, clic on the "Départ" or "Arrivée" button 
and then on map for the position. A marker will be displayed.

It is possible to remove start and end position with the trash bin icon 
on the right of the button.

It is also possible to inverse start and end position with the icon 
with the double arrows between start and stop button.

#### Tiles to visit

On the map, you can select tiles to visit, just by clicking on it. Same to
unselect a tile.

**Be carefull**: Don't add to much tiles. The time of computation increase exponentially !

#### Download route

When the route is finished ("complete" status), 
it is possible to directly download it. 

You can enter a name on the field just below the routing status and click
on the blue download icon button.
Name is optional. If none, datetime will be use for the file name and gpx name.

#### Manage route

It is also possible to store several routes in the "Routes" section.
Give a name and click on "Add" button.
Then you can highlight previous route, rename, remove or download them.

It is possible also to merge route with the "+" button:
1. select the first route
1. select thee "+" button (it will highlight it)
1. select the second route to add.
   It will add the second route to the first one and remove the second.
   You can continue by adding a third route.
1. deselect thee "+" button to exit the merge mode. 
   **Don't forget to exit merge mode** Otherwise, it will merge the next route
   you want to select. 
   
   
#### Missing KML files
veloviewer.com can export a kml file of missing tiles around your max square.
You can import this file to display directly your max square 
and the missing tiles.

## TODO list

- [ ] [Improvement] Add CANCEL to merge
- [ ] [Improvement] Add Elevation
- [ ] [Improvement] Add option to avoid turn around (Turn around price ?)
- [ ] [Improvement] Add description to buttons
- [ ] [Improvement] Add line command arguments for port
- [X] [Improvement] Add installation for python package
- [ ] [Improvement] All UI in FR or EN
- [ ] [Improvement] Add a way to reload tiles data
- [ ] [Improvement] Save routes locally
- [X] [Improvement] Direct download trace
- [X] [Bug] display if a tile has no entry point