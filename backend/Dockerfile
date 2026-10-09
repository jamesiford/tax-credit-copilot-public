# Tax Credit Copilot — API container
# Build context is the `backend/` folder (azd's default for the `api` service).

# Optional, for local use only: App Service deploys the code, not this image.
# Python 3.12 matches App Service and CI (D19).
# Pinned to bookworm DELIBERATELY. The floating `python:3.12-slim` tag moved to
# Debian 13 (trixie) in September 2026, while the Microsoft ODBC repository
# configured below is the Debian 12 (bookworm) feed. That mix installs today and
# is unsupported — a mismatched libc/OpenSSL pairing under the driver is exactly
# the kind of fault that appears first in production, not in a build log.
# Keep this tag and the repository line below on the same Debian release.
FROM python:3.12-slim-bookworm

# System deps kept minimal — FastAPI + uvicorn don't need a compiler.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ODBC Driver 18. `pyodbc` is only the wheel — the DRIVER is a system package,
# and without it every tcc_gold read fails at connect time with "Can't open
# lib". Debian 12 (bookworm) matches the python:3.11-slim base.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
 && echo "deb [arch=amd64,armhf,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
      > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && apt-get purge -y --auto-remove gnupg \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching. (OneLake access is Python-only via
# the `deltalake` wheel — no system ODBC driver needed.)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the backend tree (everything in the build context except
# entries in .dockerignore).
COPY . /app/

EXPOSE 8000

# Single uvicorn worker is fine for the demo workload; the SSE intent router
# is async and a single process scales horizontally via Container App replicas.
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
