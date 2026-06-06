FROM datasetteproject/datasette:latest

# Install Datasette plugins from PyPI
RUN pip install \
    datasette-block-robots \
    datasette-cluster-map \
    datasette-dashboards \
    datasette-graphql \
    datasette-leaflet \
    datasette-vega

# Note: the former datasette-custom-nav plugin (plugins/setup.py,
# plugins/datasette_custom_nav.py) was removed in #398. Navigation is now
# driven by datasette-metadata.json ("custom_nav_links") + datasette-custom.css,
# so no custom plugin is baked into the image.

# Default command (will be overridden by docker-compose)
CMD ["datasette", "--help"]
