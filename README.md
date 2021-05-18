# Route Tiles project

[TOC]

## Motivation

This project objective is to compute route to explore tiles, by cycling or running.
For "tiles" information, see [statshunters](https://www.statshunters.com) or [veloviewer](https://veloviewer.com).

## Installation guide

Requirements:

- python 3.7 (shapely not well manage python 3.9)


Open a terminal window and navigate to the folder that you want
to download route-tiles into.
Write in the terminal window

````shell
git clone https://github.com/BenoitBouillard/route-tiles.git
````

on future, you can perform a pull request to get the latest version:

````shell
git pull
````

followed by 

```shell
cd route-tiles
```

and at last to install python package

```shell
pip install -r requirements.txt
```


To generate html documentation from this readme:

````shell
python -m markdown README.md -f static\help.html -x extra -x toc
````


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

```shell
python route-tile-server.py
```

A message should be displayed:

```shell
serving at port 8000
```

It is possible to change the port with --port option:

```shell
>python route-tile-server.py --port 80
serving at port 80
```


### User interface

Once the server is running, it is possible to use the user interface.
It is a web page. On the same computer than the server, 
it is accessible with url [http://localhost:8000](http://localhost:8000)

To find a route, several information are mandatory or possible:

- displacement mode
- start/end position
- tiles to visit
- waypoints to go

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

- **Roadcycle**: it will use only asphalt: road, cycle path if asphalt. 
             Avoid major road
- **Road by foot**: it will use only asphalt: road, steps and path if asphalt. Allow prohibited direction.
- **Chemin**: use any path
- **Trail**: use path preferably

#### Turnaround price

For some personal reason, we could want to avoid turnaround on tile visiting 
(there is no other reason to have a turnaround on route computation), 
even if it is the minimum route. 
We could accept to do 100m or 1km more.
This option can add an additional cost for each turnaround, 
and them limit them with an acceptable cost.

/!\ The algorithm don't find the better route without turnaround (bug) /!\

#### start and end position

Start position is mandatory. End position is optional. 
If there is no end position, the route will be a loop 
(return to the start point).

To define the start or end position, clic on the "Start" or "End" button 
and then on map for the position. A marker will be displayed.

It is possible to move markers directly on the map.

It is possible to remove start and end position with the trash bin icon 
on the right of the button.

It is also possible to inverse start and end position with the icon 
with the double arrows between start and stop button.

#### Waypoints to go

You can add one or several waypoints that the route must go.

To add a waypoint, select "Add waypoint" button and then, click on the map. 
The waypoint should appear on the map by a cyan marker.

You can move a waypoint directly on the map by dragging it.

To remove a waypoint, just click on it.


#### Tiles to visit

On the map, you can select tiles to visit, just by clicking on it. Same to
unselect a tile.

**Be careful**: Don't add to much tiles. The time of computation increase exponentially !


**Tips**:

- Don't add trivial tiles
- Split your route is several ones by defining intermediate points and join then with merge function

You can remove all marked tiles with "Clear tiles" button. It will also remove all waypoints.

#### Download route

When the route is finished ("complete" status), 
it is possible to directly download it: Click on download icon blue button, and enter a file name in input field.

Name is optional. If none, datetime will be use for the file name and gpx name.

#### Manage route

It is also possible to store several routes in the "Routes" section.
Give a name and click on "+" button.
Then you can highlight previous route, rename, remove or download them.

You can also perform some operation on route with the action menu:

Actions on selected route:
- Rename selected route
- Download selected route
- Duplicate selected route (the new route will be added on the end)
- Remove selected route
- Merge the selected route with the next selected one
- Replace section of seleted route with the next selected one (Start and end of next route must be on the selecte one)
- Split the route by clicking on the map
- Cancel last action: you can cancel up to 10 actions

**Tips**: You can perform merge and replace with the finded route by clicking the green status instead of next route.
   
#### Filter displayed routes
It is possible to activate filter for displayed routes. 

Filter is a regex expression that will check route name.

Some example:
- `^Vélo`: Route started by "Vélo"
- `[0-9]$`: Route finised by a number

#### Missing tiles import
It is possible to display missing tiles on the map to facilitate the tiles selection for a route.

You can import data from statshunters:

##### StatsHunters
StatsHunters.com offer the possibility to create a link to share your personal page with others.
You have to create sharelink on [https://statshunters.com/share](https://statshunters.com/share) page and copy paste the full link
 (something like https://www.statshunters.com/share/abcdef123456) on the page and import.

As it take some time to load ativities from statshunters server, they are saved in cache to accelerate the page loading and filter computation.
To load new activities, you have to click "Reload" button.

It is possible to add filter on statshunters. 
It should be formated as python expression and usefull data from activities are:
- name
- date
- type (Run, Ride, ...)

Some examples:
- Only Ride of 2021: `type=="Ride" and date>="2021"`
- Only 2021 Run with '#fromHome' in name : `type=="Run" and '#fromHome' in name and date>"2021"`

## TODO list

- [X] [Improvement] Add CANCEL to merge => Undo up to 10 actions
- [ ] [Improvement] Add Elevation
- [X] [Improvement] Add description to buttons
- [ ] [Improvement] Add a way to reload tiles data (in case of data evolution on OSM server)
- [X] [Bug] Session management has no timeout
- [ ] [Improvement] Route management (multiple segments with tiles)
- [ ] [Improvement] Gpx import
- [X] [Bug] Forbidden chars in gpx issue
- [X] [Improvement] Add installation for python package
- [X] [Improvement] Localization in FR and EN
- [X] [Improvement] Save routes locally
- [X] [Improvement] Direct download trace
- [X] [Bug] display if a tile has no entry point
- [X] [Improvement] Add option to limit turn around (Turn around price)
- [X] [Improvement] Add line command arguments for port
- [X] [Bug] Turnaround price don't find the better route
- [X] [Improvement] Use tiles from statshunters.com
- [X] [Improvement] Add filter on saved traces
- [X] [Improvement] Display max square and cluster
- [X] [Improvement] Add circle
- [X] [Improvement] Add waypoints
- [X] [Bug] Filter selected trace could be stay displayed
- [X] [Improvement] Add insertion of route on an other
- [X] [Improvement] Add split route
- [X] [Imrpovement] Rework menu actions
