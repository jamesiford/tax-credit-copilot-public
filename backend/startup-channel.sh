#!/bin/sh
# App Service (Linux, Python 3.12) startup command for the channel gateway. [CH-06]
# One worker by default: the fact ledger (verify_figures) and the rate limiter are
# per process, so with N workers a conversation's facts live in one of N and the
# effective rate limit is N times the setting. Raise WEB_CONCURRENCY only knowing that.
set -e
cd "$(dirname "$0")"
exec gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-1} -b 0.0.0.0:${PORT:-8000} --timeout 120 channel.main:app
