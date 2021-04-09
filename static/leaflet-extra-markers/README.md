# Leaflet.extra-markers

<a href="https://github.com/lvoogdt/Leaflet.awesome-markers">Big Thanks to lvoogdt of Leaflet.awesome-markers</a>

![ExtraMarkers screenshot](https://raw.github.com/coryasilva/Leaflet.ExtraMarkers/master/screenshot.png "Screenshot of ExtraMarkers")

**<a href="http://coryasilva.github.io/Leaflet.ExtraMarkers/" target="_blank">Demo</a>**

## Icons

Leaflet.extra-markers is designed for:

- [Bootstrap 3 icons](http://twitter.github.com/bootstrap/)
- [Font Awesome 4.x](http://fortawesome.github.com/Font-Awesome/)
- [Font Awesome 5.x](http://fortawesome.github.com/Font-Awesome/)
- [Semantic UI 2.x icons](http://semantic-ui.com/)
- [Ion Icons 2.x](http://ionicons.com/)
- Leaflet 0.5-Latest

## Using the plugin

### 1. Requirements

Follow the [getting started guide](#icons) for the desired font library and make sure its included in your project.

### 2. Installing Leaflet.extra-markers

Next, copy the `dist/img` directory, `/dist/css/leaflet.extra-markers.min.css`, and `/dist/js/leaflet.extra-markers.min.js` to your project and include them:

````xml
<link rel="stylesheet" href="css/leaflet.extra-markers.min.css">
````

or

````less
@import 'bower_components/src/assets/less/Leaflet.extra-markers.less
````

and

````xml
<script src="js/leaflet.extra-markers.min.js"></script>
````

### 3. Creating a Marker

Now use the plugin to create a marker like this:

````js
  // Creates a red marker with the coffee icon
  var redMarker = L.ExtraMarkers.icon({
    icon: 'fa-coffee',
    markerColor: 'red',
    shape: 'square',
    prefix: 'fa'
  });

  L.marker([51.941196,4.512291], {icon: redMarker}).addTo(map);
````

---

## Properties

| Property        | Description                                 | Default Value | Possible  values                                     |
| --------------- | ------------------------------------------- | ------------- | ---------------------------------------------------- |
| extraClasses    | Additional classes in the created `<i>` tag | `''`          | `fa-rotate90 myclass`; space delimited classes to add |
| icon            | Name of the icon **with** prefix            | `''`          | `fa-coffee` (see icon library's documentation)  |
| iconColor       | Color of the icon                           | `'white'`     | `'white'`, `'black'` or css code (hex, rgba etc) |
| iconRotation    | Rotates the icon with css transformations   | `0`           | numeric degrees
| innerHTML       | Custom HTML code                            | `''`          | `<svg>`, images, or other HTML; a truthy assignment will override the default html icon creation behavior |
| markerColor     | Color of the marker (css class)             | `'blue'`      | `'red'`, `'orange-dark'`, `'orange'`, `'yellow'`, `'blue-dark'`, `'cyan'`, `'purple'`, `'violet'`, `'pink'`, `'green-dark'`, `'green'`, `'green-light'`, `'black'`, `'white'`, or color hex code **if `svg` is true** |
| number          | Instead of an icon, define a plain text     | `''`          | `'1'` or `'A'`, must set `icon: 'fa-number'` |
| prefix          | The icon library's base class               | `'glyphicon'` | `fa` (see icon library's documentation) |
| shape           | Shape of the marker (css class)             | `'circle'`    | `'circle'`, `'square'`, `'star'`, or `'penta'` |
| svg             | Use SVG version                             | `false`       | true or false
| svgBorderColor  | (DEPRECATED has not effect)                 | `'#fff'`      | any valid hex color
| svgOpacity      | (DEPRECATED has not effect)                 | `1`           | decimal range from 0 to 1

## License

- Leaflet.ExtraMarkers and colored markers are licensed under the MIT License - http://opensource.org/licenses/mit-license.html.
