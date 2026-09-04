FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Recordings, HLS segments and camera config live here. Mount your hard
# drive on this path (see docker-compose.yml).
VOLUME ["/data"]
ENV NVR_DATA_DIR=/data

EXPOSE 8000

# `python -m app.main` behaves exactly like the plain `uvicorn app.main:app`
# invocation (host/port still come from NVR_HOST/NVR_PORT, defaulting to
# the same 0.0.0.0:8000) unless NVR_SSL_CERTFILE/NVR_SSL_KEYFILE are also
# set, in which case it serves native HTTPS - see
# scripts/generate-self-signed-cert.sh.
CMD ["python", "-m", "app.main"]
