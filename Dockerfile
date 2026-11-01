# Build stage: compile mysqlclient and the rest of requirements.txt into a venv
FROM python:3.14-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Runtime stage
FROM python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --no-create-home app

COPY --from=build /venv /venv
WORKDIR /app
COPY identity ./identity

ENV PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

# identity/config.py is not in the image: mount it at /app/identity/config.py.
# ENCRYPTION_KEY must be set in the environment so startup doesn't prompt.
# Numeric UID (the "app" user) so Kubernetes' runAsNonRoot can verify it
USER 10001
EXPOSE 8000

# One worker only: the APScheduler cron jobs run inside the app process,
# so more workers would run each job more than once
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", \
     "--access-logfile", "-", "identity:app"]
