FROM python:3.13-slim AS build
WORKDIR /build
COPY pyproject.toml README.md VERSION ./
COPY src ./src
RUN pip wheel --no-cache-dir --wheel-dir /wheels .

FROM python:3.13-slim
RUN groupadd -r colf-manager && useradd -r -g colf-manager -d /app colf-manager
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
RUN mkdir -p /data && chown colf-manager:colf-manager /data
USER colf-manager
ENV COLF_MANAGER_DATA=/data PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["gunicorn","--bind=0.0.0.0:8000","--workers=2","--threads=4","--access-logfile=-","colf_manager.app:create_app()"]
