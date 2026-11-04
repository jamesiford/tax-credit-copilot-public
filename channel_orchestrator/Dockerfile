# Container build of the orchestrator, for the container deployment path and for a local build.
# The recommended deployment is the source-code (zip) path, which needs no registry; see README.md.
#
#   python scripts/vendor-orchestrator.py          # copy the shared modules in first
#   docker build --platform linux/amd64 -t tcc-channel-orchestrator channel_orchestrator
#
# The hosted-agent runtime contract: the Responses protocol on 8088, GET /readiness, SIGTERM
# for graceful shutdown. Hosted agents run linux/amd64, hence the --platform on the build.
FROM python:3.13-slim

# Python must not read a user site-packages directory: dependencies are installed in the image.
ENV PYTHONNOUSERSITE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 agent
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY app ./app
# The build fails here, not at the first question, if the shared modules were not vendored.
RUN test -f app/vendor/tcc_shared/MANIFEST.json

USER agent
EXPOSE 8088
CMD ["python", "main.py"]
