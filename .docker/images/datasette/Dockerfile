FROM datasetteproject/datasette:latest

# Install Datasette plugins from PyPI
RUN pip install \
    datasette-block-robots \
    datasette-cluster-map \
    datasette-dashboards \
    datasette-graphql \
    datasette-leaflet

# Default command (will be overridden by docker-compose)
CMD ["datasette", "--help"]
