FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY scripts/requirements.txt /tmp/requirements-scripts.txt
COPY requirements-web.txt /tmp/requirements-web.txt
RUN pip install -r /tmp/requirements-scripts.txt -r /tmp/requirements-web.txt

COPY . /app

RUN mkdir -p /app/scanned /app/scanned/archive

EXPOSE 8000
CMD ["sh", "-c", "uvicorn web.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
