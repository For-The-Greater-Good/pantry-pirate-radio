from datasette import hookimpl


@hookimpl
def menu_links(datasette, actor, request):
    """Add custom navigation links to Datasette menu."""
    return [
        {
            "href": datasette.urls.path("/pantry_pirate_radio/location_master"),
            "label": "📍 All Locations",
        },
        {
            "href": "https://datasette.for-the-gg.org/map.html",
            "label": "🗺️ Interactive Map",
        },
        {
            "href": "https://github.com/For-The-Greater-Good/pantry-pirate-radio",
            "label": "🏴‍☠️ Pantry Pirate Radio",
        },
        {
            "href": "https://github.com/For-The-Greater-Good/HAARRRvest",
            "label": "📊 HAARRRvest Data",
        },
    ]