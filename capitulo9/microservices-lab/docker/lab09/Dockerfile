ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE} AS builder
ARG SERVICE
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
COPY ${SERVICE}/requirements.lab09.lock /build/requirements.lock
RUN /opt/venv/bin/pip install --only-binary=:all: -r /build/requirements.lock

FROM ${PYTHON_IMAGE} AS runtime
ARG SERVICE
ARG APP_PORT
ARG APP_VERSION=9.0.0
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    APP_PORT=${APP_PORT}
LABEL org.opencontainers.image.version="${APP_VERSION}"
RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid 10001 --create-home appuser
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=10001:10001 ${SERVICE}/ /app/
COPY --chown=10001:10001 shared/ /app/shared/
RUN printf '%s\n' "$APP_VERSION" > /app/BUILD_VERSION
USER 10001:10001
EXPOSE ${APP_PORT}
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ['APP_PORT']+'/health',timeout=3)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"$APP_PORT\""]
