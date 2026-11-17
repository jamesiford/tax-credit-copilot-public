FROM --platform=$BUILDPLATFORM mcr.microsoft.com/dotnet/sdk:10.0.404@sha256:fe0fd4e93bd2fbb47c883b7a6369e5c8d3db8bf01cdc5981f6ee35fbdf3ff4fb AS build
WORKDIR /src/dotnet
COPY dotnet/ ./
COPY backend/data/source/mapping/default.json /src/backend/data/source/mapping/default.json
COPY packages/ /packages/
ARG NUGET_SOURCE=https://api.nuget.org/v3/index.json
ARG NUGET_AUDIT=true
RUN test "$(dotnet --version)" = "10.0.404" && dotnet publish src/TaxCredit.Orchestrator/TaxCredit.Orchestrator.csproj -c Release -r linux-x64 --self-contained false -p:UseAppHost=false -p:ContinuousIntegrationBuild=true -p:RestorePackagesWithLockFile=true -p:RestoreLockedMode=true -p:NuGetAudit=$NUGET_AUDIT --source "$NUGET_SOURCE" -o /out --nologo -v:q
COPY containers/start-orchestrator.sh containers/probe.sh /out/
COPY telemetry/ /src/telemetry/
RUN dotnet publish /src/telemetry/Hook/TaxCredit.Deployment.Telemetry.csproj -c Release -o /out/telemetry --source /packages --nologo -v:q -p:NuGetAudit=false
FROM mcr.microsoft.com/dotnet/aspnet:10.0@sha256:bfd912c83295ce66d4b706ebb8541b9f14259b0e76fbb88b2751f58ce2399d2e AS runtime
USER root
RUN apt-get update -qq && apt-get install -y --no-install-recommends curl ca-certificates >/dev/null && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /out/ ./
ARG GIT_COMMIT=working-tree
LABEL org.opencontainers.image.revision=$GIT_COMMIT
ENV CHANNEL_DEBUG_WHOAMI=false \
    KNOWLEDGE_ENABLED=false KNOWLEDGE_PROVIDER=none AI_INJECTION_GUARD=on AI_OUTPUT_POLICY=on \
    AI_GATEWAY_TLS_VERIFY=true GIT_COMMIT=$GIT_COMMIT Logging__LogLevel__Default=None
RUN find . -type f ! -name checksums.sha256 -print0 | sort -z | xargs -0 sha256sum > /app/checksums.sha256
USER app
EXPOSE 8088
HEALTHCHECK --interval=30s --timeout=4s --start-period=30s CMD ["sh", "/app/probe.sh", "8088", "/readiness"]
ENTRYPOINT ["sh", "/app/start-orchestrator.sh"]
