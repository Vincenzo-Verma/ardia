FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# requirements.txt is at project root; build context must be project root
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

COPY backend/ /app/

COPY document-gen/ /document-gen/
RUN cd /document-gen && npm install

WORKDIR /app

ENV PYTHONPATH=/app
