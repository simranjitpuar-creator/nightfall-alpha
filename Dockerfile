FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NIGHTFALL_ALPHA_ENV=production \
    NIGHTFALL_ALPHA_DATA_DIR=/var/lib/nightfall-alpha \
    NIGHTFALL_ALPHA_SEED_DATA_DIR=/app/seed-data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY config ./config
COPY data/universe ./data/universe
COPY src ./src
COPY scripts/cloud_run_start.py ./scripts/cloud_run_start.py

RUN python -m pip install --no-cache-dir -e . \
    && mkdir -p /app/seed-data/universe \
    && cp /app/data/universe/*.csv /app/seed-data/universe/ \
    && NIGHTFALL_ALPHA_DATA_DIR=/app/seed-data nightfall-alpha backtest \
         --data-source synthetic --symbols 25 --start 2018-01-01 --end 2025-12-31 \
    && groupadd --gid 10001 nightfall \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin nightfall \
    && mkdir -p /var/lib/nightfall-alpha \
    && chown -R 10001:10001 /app /var/lib/nightfall-alpha

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["python", "scripts/cloud_run_start.py"]
