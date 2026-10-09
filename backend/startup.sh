#!/bin/sh
# App Service (Linux, Python 3.12) startup command for the API. [HOST-1]
# Gunicorn supervises uvicorn workers; App Service sets PORT. The long timeout
# covers a client calculation run, which is synchronous and can take minutes.
set -e
cd "$(dirname "$0")"
exec gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-8000} --timeout 600 main:app
