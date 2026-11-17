"""Offline deployment lint: emit setting names only, never configuration contents."""

import argparse
import json
import re
import sys
from pathlib import Path

from checks import allowlist, audience, flag, guid, https, number, resources
from contract import SERVICES, inventory
from model_checks import validate_models

SHARED_REQUIRED = ("ENVIRONMENT", "DATA_CLASSIFICATION", "AUTH_MODE",
                   "TCC_PERSISTENCE_PROVIDER", "FABRIC_SQL_SERVER", "FABRIC_SQL_DATABASE",
                   "SOURCE_SQL_SERVER", "SOURCE_SQL_DATABASE", "DATA_SOURCE", "ARTIFACT_STORE",
                   "ARTIFACT_BLOB_ACCOUNT_URL", "AUTH_TENANT_ID", "API_AUDIENCE",
                   "TCC_REPOSITORY_ROOT", "AZURE_CLIENT_ID", "GIT_COMMIT",
                   "CHANNEL_WRITER_SOURCE", "CHANNEL_ENFORCE_WRITER_FOR_USERS")


def validate(settings, service, deployed=True, check_resources=False):
    """Validate an explicit emission manifest, not an unrestricted process environment."""
    errors = set()
    if service not in SERVICES:
        return ["service"]
    if not isinstance(settings, dict):
        return ["configuration"]
    errors = validate_names(settings, service)
    if errors:
        return sorted(errors)
    if service == "orchestrator":
        validate_orchestrator(settings, errors, deployed)
    else:
        validate_runtime(settings, errors, deployed)
    if deployed:
        validate_emission(settings, errors)
    if service in ("api", "gateway"):
        validate_listener(settings, errors)
        validate_origins(settings, "CORS_ORIGINS", errors)
    if service == "gateway":
        validate_channel(settings, errors, deployed)
    if check_resources and service != "orchestrator":
        resources(settings, errors)
    return sorted(errors)


def validate_names(settings, service):
    errors = set()
    known = inventory()
    for name, value in settings.items():
        if name not in known:
            errors.add(name if re.fullmatch(r"[A-Z][A-Z_0-9]*", name) else "configuration")
        elif not isinstance(value, str):
            errors.add(name)
        elif (known[name]["per_service"][service]["classification"] in ("unsupported", "Python-ops-only", "irrelevant")
              or known[name]["classification"] == "translated" and "target" in known[name]
              or service not in known[name]["service_scope"]):
            errors.add(name)
    return errors


def validate_emission(settings, errors):
    for name in ("TCC_CONTRACT_HOOKS", "TCC_WORKER_ONCE"):
        if name in settings and settings[name] not in ("", "0"):
            errors.add(name)
    if settings.get("TCC_FEATURE_ASSEMBLIES", ""):
        errors.add("TCC_FEATURE_ASSEMBLIES")
    for name in ("OPERATIONAL_DB", "ARTIFACT_LOCAL_ROOT", "PAYROLL_PATH"):
        if name in settings:
            errors.add(name)
    for name, value in settings.items():
        if name.startswith("Logging__") and value != "None":
            errors.add(name)
    if "ASPNETCORE_ENVIRONMENT" in settings and settings["ASPNETCORE_ENVIRONMENT"] != "Production":
        errors.add("ASPNETCORE_ENVIRONMENT")
    if flag(settings, "SCM_DO_BUILD_DURING_DEPLOYMENT", errors):
        errors.add("SCM_DO_BUILD_DURING_DEPLOYMENT")
    if "WEBSITE_RUN_FROM_PACKAGE" in settings and settings["WEBSITE_RUN_FROM_PACKAGE"] != "1":
        errors.add("WEBSITE_RUN_FROM_PACKAGE")


def validate_origins(settings, name, errors):
    for origin in filter(None, (x.strip() for x in settings.get(name, "").split(","))):
        if not https(origin, origin=True) or origin.endswith("/"):
            errors.add(name)


def required(settings, names, errors):
    errors.update(name for name in names if not settings.get(name, "").strip())


def validate_runtime(settings, errors, deployed):
    if deployed:
        required(settings, SHARED_REQUIRED, errors)
        if settings.get("ENVIRONMENT") in ("", "local", None):
            errors.add("ENVIRONMENT")
        for name, value in (("TCC_PERSISTENCE_PROVIDER", "warehouse"),
                            ("DATA_SOURCE", "lakehouse"), ("ARTIFACT_STORE", "blob"),
                            ("AUTH_MODE", "entra")):
            if settings.get(name) != value:
                errors.add(name)
        if settings.get("DATA_CLASSIFICATION") not in ("customer", "synthetic"):
            errors.add("DATA_CLASSIFICATION")
        if not flag(settings, "CHANNEL_ENFORCE_WRITER_FOR_USERS", errors, runtime=True):
            errors.add("CHANNEL_ENFORCE_WRITER_FOR_USERS")
        if not allowlist(settings.get("CLIENT_ALLOWLIST", "")):
            errors.add("CLIENT_ALLOWLIST")
    else:
        flag(settings, "CHANNEL_ENFORCE_WRITER_FOR_USERS", errors, runtime=True)
    validate_runtime_trust(settings, errors)
    validate_runtime_paths(settings, errors, deployed)


def validate_runtime_trust(settings, errors):
    for name in ("AUTH_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_TENANT_ID"):
        if name in settings and not guid(settings[name]):
            errors.add(name)
    if "API_AUDIENCE" in settings and not all(
            audience(x.strip()) for x in settings["API_AUDIENCE"].split(",")):
        errors.add("API_AUDIENCE")
    if "ARTIFACT_BLOB_ACCOUNT_URL" in settings and not https(
            settings["ARTIFACT_BLOB_ACCOUNT_URL"], origin=True):
        errors.add("ARTIFACT_BLOB_ACCOUNT_URL")
    if settings.get("CHANNEL_WRITER_SOURCE", "allowlist") not in ("allowlist", "entra_group", "either"):
        errors.add("CHANNEL_WRITER_SOURCE")
    if settings.get("CHANNEL_WRITER_SOURCE", "allowlist") != "allowlist" and not guid(
            settings.get("CHANNEL_WRITER_GROUP_ID", "")):
        errors.add("CHANNEL_WRITER_GROUP_ID")


def validate_runtime_paths(settings, errors, deployed):
    schema = settings.get("SOURCE_SCHEMA", "tcc_source").strip()
    if schema and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,127}", schema):
        errors.add("SOURCE_SCHEMA")
    for name in ("TCC_REPOSITORY_ROOT", "RULES_DIR", "TCC_SEED_ROOT", "GIT_COMMIT"):
        if name in settings and not settings[name].strip():
            errors.add(name)
    if "PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER" in settings:
        if not flag(settings, "PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER", errors) and deployed:
            errors.add("PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER")
    for name in ("PAY_CODE_POLICY", "FISCAL_RULES_POLICY"):
        if name in settings and settings[name] not in ("strict", "assume"):
            errors.add(name)
    number(settings, "RATE_LIMIT_PER_MINUTE", errors, 0, 1000000, integer=True)
    number(settings, "RUN_STALE_WORKER_SECONDS", errors, 1, 2147483647, integer=True)


def validate_listener(settings, errors):
    value = settings.get("ASPNETCORE_URLS", "")
    if not re.fullmatch(r"http://(?:0\.0\.0\.0|127\.0\.0\.1|\[::\]):[1-9][0-9]{0,4}", value):
        errors.add("ASPNETCORE_URLS")
    elif int(value.rsplit(":", 1)[1]) > 65535:
        errors.add("ASPNETCORE_URLS")


def validate_channel(settings, errors, deployed):
    required(settings, ("TENANT_ID", "GATEWAY_AUDIENCE"), errors)
    if not guid(settings.get("TENANT_ID", "")):
        errors.add("TENANT_ID")
    if not audience(settings.get("GATEWAY_AUDIENCE", "")):
        errors.add("GATEWAY_AUDIENCE")
    if settings.get("TENANT_ID", "").lower() != settings.get("AUTH_TENANT_ID", "").lower():
        errors.update(("TENANT_ID", "AUTH_TENANT_ID"))
    if flag(settings, "CHANNEL_DEBUG_WHOAMI", errors) and deployed:
        errors.add("CHANNEL_DEBUG_WHOAMI")
    number(settings, "CHANNEL_RATE_LIMIT_PER_MINUTE", errors, 1, 6000, integer=True)
    validate_origins(settings, "CHANNEL_MCP_ALLOWED_ORIGINS", errors)
    for app in filter(None, (x.strip() for x in settings.get("CHANNEL_ALLOWED_CALLER_APP_IDS", "").split(","))):
        if not guid(app):
            errors.add("CHANNEL_ALLOWED_CALLER_APP_IDS")
    seen = set()
    for binding in filter(None, (x.strip() for x in settings.get("CHANNEL_CALLER_CHANNELS", "").split(","))):
        pair = binding.split("=")
        if (len(pair) != 2 or not guid(pair[0]) or pair[0].lower() in seen
                or not pair[1] or any(x not in ("teams", "m365-copilot") for x in pair[1].split("|"))):
            errors.add("CHANNEL_CALLER_CHANNELS")
        seen.add(pair[0].lower())


def validate_orchestrator(settings, errors, deployed):
    required(settings, ("TENANT_ID", "CHANNEL_GATEWAY_URL", "CHANNEL_GATEWAY_AUDIENCE"), errors)
    if not guid(settings.get("TENANT_ID", "")):
        errors.add("TENANT_ID")
    if not https(settings.get("CHANNEL_GATEWAY_URL", "")):
        errors.add("CHANNEL_GATEWAY_URL")
    if not audience(settings.get("CHANNEL_GATEWAY_AUDIENCE", "")):
        errors.add("CHANNEL_GATEWAY_AUDIENCE")
    if "AZURE_CLIENT_ID" in settings and not guid(settings["AZURE_CLIENT_ID"]):
        errors.add("AZURE_CLIENT_ID")
    if flag(settings, "CHANNEL_DEBUG_WHOAMI", errors) and deployed:
        errors.add("CHANNEL_DEBUG_WHOAMI")
    if settings.get("CHANNEL_NAME", "teams").strip() not in ("teams", "m365-copilot"):
        errors.add("CHANNEL_NAME")
    sources = settings.get("CHANNEL_IDENTITY_SOURCES", "original-subject,platform,agent-user-id")
    if not sources.strip() or any(x.strip() not in ("original-subject", "platform", "agent-user-id", "client-headers")
                                  for x in sources.split(",")):
        errors.add("CHANNEL_IDENTITY_SOURCES")
    if deployed and "client-headers" in sources.split(","):
        errors.add("CHANNEL_IDENTITY_SOURCES")
    validate_models(settings, errors, deployed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", choices=SERVICES)
    parser.add_argument("--file", type=Path, help="Explicit JSON settings object; never dump process environment")
    parser.add_argument("--inventory", action="store_true", help="Expand reviewed inventory to per-name JSON records")
    parser.add_argument("--local", action="store_true", help="Synthetic/local lint; not deployment approval")
    parser.add_argument("--check-resources", action="store_true")
    args = parser.parse_args(argv)
    if args.inventory:
        print(json.dumps(list(inventory().values()), indent=2))
        return 0
    try:
        settings = json.loads(args.file.read_text(encoding="utf-8")) if args.file else None
        errors = validate(settings, args.service, not args.local, args.check_resources)
    except (OSError, ValueError, TypeError, RecursionError):
        errors = ["configuration"]
    print(json.dumps({"valid": not errors, "settings": errors}, separators=(",", ":")))
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
