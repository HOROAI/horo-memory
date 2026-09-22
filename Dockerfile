FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 horo
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY static ./static

RUN pip install ".[graphify]"

RUN mkdir -p /data && chown -R horo:horo /app /data
USER horo

EXPOSE 8088
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health', timeout=3)"

CMD ["horo-memory", "serve"]

