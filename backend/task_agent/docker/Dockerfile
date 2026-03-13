FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workdir/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

CMD ["sh", "-lc", "trap : TERM INT; while sleep 3600; do :; done"]
