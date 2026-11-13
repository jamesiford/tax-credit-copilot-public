#!/bin/sh
# App Service (Linux, Python 3.12) startup command for the run worker. [ADR-012]
# One process: it leases queued batch items and runs them through the existing run and assess commands. App Service
# sets PORT; the worker answers /healthz there so the platform can see it is alive.
set -e
cd "$(dirname "$0")"
exec python -m bootstrap.run_worker --health-port "${PORT:-8000}"
