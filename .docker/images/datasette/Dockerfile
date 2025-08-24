FROM datasetteproject/datasette:latest

# Install Datasette plugins from PyPI
RUN pip install \
    datasette-block-robots \
    datasette-cluster-map \
    datasette-dashboards \
    datasette-graphql \
    datasette-leaflet \
    datasette-vega

# Copy and install custom plugin
WORKDIR /tmp/plugin
COPY plugins/setup.py plugins/datasette_custom_nav.py ./
RUN pip install -e .
WORKDIR /

# Default command (will be overridden by docker-compose)
CMD ["datasette", "--help"]
