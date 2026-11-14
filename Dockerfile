FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
RUN pip install -r requirements.lock && pip install --no-deps . && useradd --uid 10001 --create-home headroom && mkdir /app/runtime && chown headroom:headroom /app/runtime
COPY config ./config
COPY data ./data
COPY fixtures ./fixtures
USER headroom
ENV HEADROOM_DATA_DIR=/app/runtime HEADROOM_PROVIDER=fake
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s CMD python -c "import os,urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/health', headers={'x-api-key':os.getenv('HEADROOM_API_KEY','')}); urllib.request.urlopen(r, timeout=2)"
CMD ["uvicorn", "covenants.api:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test
USER root
RUN pip install '.[test]'
COPY tests ./tests
COPY scripts ./scripts
RUN chown -R headroom:headroom /app
USER headroom
CMD ["pytest"]

