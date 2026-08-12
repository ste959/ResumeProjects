# Research service image. Build context is research/ so it can copy both the mds package and the
# service:   docker build -f service/Dockerfile -t bonddesk-research .
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Install the research layer's pinned deps + the web framework.
COPY requirements.txt ./requirements.txt
COPY service/requirements.txt ./service-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r service-requirements.txt

# The research modules and the service (snapshot.json is included when present — the told-story cache).
COPY mds ./mds
COPY service ./service

# The columnar warehouse (bars/fundamentals/macro/options) is mounted read-only at runtime as
# /app/data so live backtests work; the baked snapshot.json covers the told-story views regardless.

# Run as an unprivileged user (mirrors the Java images) so a container compromise doesn't start as
# root. Done after COPY so the copied files stay owned by root and aren't writable by the app user.
RUN useradd --system --uid 1001 --create-home appuser
USER appuser

EXPOSE 8082
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8082"]
