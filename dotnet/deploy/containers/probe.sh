#!/bin/sh
set -eu
# curl is installed in the HTTP images, and never prints a response body or URL.
exec curl --silent --fail --max-time 3 --output /dev/null "http://127.0.0.1:${1:-8080}${2:-/api/health}"
