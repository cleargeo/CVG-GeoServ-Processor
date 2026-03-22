# =============================================================================
# CVG GeoServ Processor — Docker Image
# (c) Clearview Geographic LLC — All Rights Reserved | Est. 2018
# =============================================================================
FROM python:3.13-slim

LABEL maintainer="azelenski@clearviewgeographic.com"
LABEL org="Clearview Geographic, LLC"
LABEL version="1.0.0"
LABEL description="CVG GeoServ Processor — centralized geoprocessing engine"

# System deps: GDAL/GEOS for rasterio + fiona + geopandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libspatialindex-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python deps first (layer cache)
COPY pyproject.toml requirements-lock.txt* ./
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir \
    rasterio numpy click fastapi "uvicorn[standard]" pydantic geopandas shapely fiona scikit-image

# Copy source
COPY geoserv_processor/ ./geoserv_processor/

# Healthcheck: port 8003
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8003/health')" || exit 1

EXPOSE 8003

CMD ["python", "-m", "geoserv_processor.cli", "web", "--host", "0.0.0.0", "--port", "8003"]
