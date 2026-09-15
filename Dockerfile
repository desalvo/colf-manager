FROM python:3.13-slim AS build

WORKDIR /build

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get -y upgrade \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --upgrade pip setuptools wheel

COPY pyproject.toml README.md VERSION ./
COPY src ./src

RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive

# Apply Debian security updates available at image build time.
RUN apt-get update \
    && apt-get -y upgrade \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 colf-manager \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /app --shell /usr/sbin/nologin colf-manager

WORKDIR /app

COPY --from=build /wheels /wheels
COPY migrations /app/migrations

# Install only application/runtime dependencies. Do not add packaging-only
# libraries to the runtime image.
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels /root/.cache/pip

RUN mkdir -p /data && chown colf-manager:colf-manager /data

USER 10001:10001

ENV COLF_MANAGER_DATA=/data \
    TMPDIR=/data/tmp \
    TMP=/data/tmp \
    TEMP=/data/tmp \
    COLF_MANAGER_PRODUCTION=1 \
    PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"

CMD ["sh","-c","mkdir -p /data/tmp && exec gunicorn --bind=0.0.0.0:8000 --workers=${GUNICORN_WORKERS:-2} --threads=${GUNICORN_THREADS:-4} --timeout=${GUNICORN_TIMEOUT:-60} --access-logfile=- --error-logfile=- 'colf_manager.app:create_app()'"]
