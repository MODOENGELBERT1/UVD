FROM python:3.11-slim
WORKDIR /app
# rasterio/GDAL ont besoin de libexpat1 (absente de python:3.11-slim)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR \
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif,.TIF,.tiff \
    GDAL_HTTP_MULTIPLEX=YES \
    VSI_CACHE=TRUE \
    GDAL_CACHEMAX=64 \
    VSI_CACHE_SIZE=33554432 \
    PORT=8000
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# ${PORT:-8000} : évite un crash si PORT n'est pas fourni ; 1 worker (mémoire réduite)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
