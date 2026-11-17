"""Validate the orchestrator's real model factory, never the API's offline registry."""

import re

from checks import audience, flag, headers, https, number

ROLES = ("ROUTER", "NARRATOR", "ANALYSIS")
INTEGERS = {
    "CHANNEL_MAX_TOOL_CALLS": (1, 20), "CHANNEL_CONFIRM_TTL_SECONDS": (30, 3600),
    "CHANNEL_STATE_TTL_SECONDS": (60, 86400), "CHANNEL_REQUEST_TIMEOUT_SECONDS": (5, 300),
    "CHANNEL_TURN_TIMEOUT_SECONDS": (10, 600), "KNOWLEDGE_TOP": (1, 10),
    "AI_RETRY_MAX_ATTEMPTS": (1, 10), "AI_BULKHEAD_MAX_CONCURRENT": (1, 1000),
    "AI_BREAKER_FAILURE_THRESHOLD": (1, 1000),
}
SECONDS = ("AI_CALL_TIMEOUT_SECONDS", "AI_TOTAL_DEADLINE_SECONDS",
           "AI_BREAKER_RESET_SECONDS", "AI_GATEWAY_TIMEOUT_SECONDS",
           "AI_GATEWAY_CONNECT_TIMEOUT_SECONDS")


def text(settings, name, default=""):
    return settings.get(name, "").strip() or default


def validate_models(settings, errors, deployed):
    for name in ("AI_INJECTION_GUARD", "AI_OUTPUT_POLICY"):
        if text(settings, name, "on").lower() != "on":
            errors.add(name)
    egress = text(settings, "AI_EGRESS_POLICY", "allow_all")
    if egress not in ({"aggregates_only", "block"} if deployed else
                      {"allow_all", "aggregates_only", "block"}):
        errors.add("AI_EGRESS_POLICY")
    for name in ("AI_TOKEN_BUDGET_DAILY", "AI_TOKEN_BUDGET_PER_PRINCIPAL_DAILY"):
        if deployed and not text(settings, name):
            errors.add(name)
        number(settings, name, errors, 0, 9223372036854775807, integer=True)
    for name, (low, high) in INTEGERS.items():
        number(settings, name, errors, low, high, integer=True)
    for name in SECONDS:
        number(settings, name, errors, 1e-12, 3600)
    for name in ("AI_RETRY_BASE_SECONDS", "AI_RETRY_MAX_SECONDS"):
        number(settings, name, errors, 0, 3600)
    providers = validate_chains(settings, errors)
    if "foundry" in providers and not https(text(settings, "FOUNDRY_PROJECT_ENDPOINT")):
        errors.add("FOUNDRY_PROJECT_ENDPOINT")
    if "gateway" in providers:
        validate_gateway(settings, errors, deployed)
    validate_knowledge(settings, errors, deployed)


def validate_chains(settings, errors):
    providers = set()
    for role in ROLES:
        chain_key = "AI_PROVIDER_CHAIN__" + role
        chain = text(settings, chain_key, text(settings, "AI_PROVIDER_CHAIN", "foundry"))
        names = [name.strip().lower() for name in chain.split(",") if name.strip()]
        if not names or any(name not in ("foundry", "gateway") for name in names):
            errors.add(chain_key if chain_key in settings else "AI_PROVIDER_CHAIN")
        providers.update(names)
        for provider in names:
            model_key = "AI_MODEL_" + role + "__" + provider.upper()
            fallback = text(settings, "FOUNDRY_MODEL",
                            text(settings, "AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini"))
            if not text(settings, model_key, text(settings, "AI_MODEL_" + role,
                                                 fallback if provider == "foundry" else "")):
                errors.add(model_key)
    return providers


def validate_knowledge(settings, errors, deployed):
    hosts = [x.strip() for x in text(settings, "AI_OUTPUT_ALLOWED_HOSTS").split(",") if x.strip()]
    if any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", x) for x in hosts):
        errors.add("AI_OUTPUT_ALLOWED_HOSTS")
    if flag(settings, "KNOWLEDGE_ENABLED", errors):
        if deployed or text(settings, "KNOWLEDGE_PROVIDER", "none") != "fake":
            errors.add("KNOWLEDGE_ENABLED")
    if text(settings, "KNOWLEDGE_PROVIDER", "none").lower() not in ("none", "fake", "foundry-iq"):
        errors.add("KNOWLEDGE_PROVIDER")


def validate_gateway(settings, errors, deployed):
    if not https(text(settings, "AI_GATEWAY_ENDPOINT"), origin=True):
        errors.add("AI_GATEWAY_ENDPOINT")
    auth = text(settings, "AI_GATEWAY_AUTH")
    if auth not in ("none", "api_key", "oauth_client_credentials", "entra_token"):
        errors.add("AI_GATEWAY_AUTH")
    if deployed and auth != "entra_token":
        errors.add("AI_GATEWAY_AUTH")
    if deployed:
        errors.update(name for name in ("AI_GATEWAY_API_KEY", "AI_GATEWAY_OAUTH_CLIENT_SECRET")
                      if name in settings)
    if auth == "api_key" and not text(settings, "AI_GATEWAY_API_KEY"):
        errors.add("AI_GATEWAY_API_KEY")
    if auth == "api_key":
        header = text(settings, "AI_GATEWAY_API_KEY_HEADER", "Authorization")
        if not re.fullmatch(r"[A-Za-z0-9-]+", header):
            errors.add("AI_GATEWAY_API_KEY_HEADER")
        if any(c in settings.get("AI_GATEWAY_API_KEY_PREFIX", "") for c in "\r\n"):
            errors.add("AI_GATEWAY_API_KEY_PREFIX")
    if auth == "oauth_client_credentials":
        for name in ("AI_GATEWAY_OAUTH_CLIENT_ID", "AI_GATEWAY_OAUTH_CLIENT_SECRET"):
            if not text(settings, name):
                errors.add(name)
        if not https(text(settings, "AI_GATEWAY_OAUTH_TOKEN_URL")):
            errors.add("AI_GATEWAY_OAUTH_TOKEN_URL")
    if auth == "entra_token":
        value = text(settings, "AI_GATEWAY_ENTRA_AUDIENCE")
        if not (audience(value) or https(value, origin=True)):
            errors.add("AI_GATEWAY_ENTRA_AUDIENCE")
    if text(settings, "AI_GATEWAY_API_STYLE", "openai_v1") not in ("openai_v1", "azure_deployments"):
        errors.add("AI_GATEWAY_API_STYLE")
    for name in ("AI_GATEWAY_TLS_VERIFY", "AI_GATEWAY_STREAMING", "AI_GATEWAY_SUPPORTS_TOOLS"):
        value = flag(settings, name, errors) if text(settings, name) else True
        if name == "AI_GATEWAY_TLS_VERIFY" and not value:
            errors.add(name)
    if text(settings, "AI_GATEWAY_EXTRA_HEADERS") and not headers(settings["AI_GATEWAY_EXTRA_HEADERS"]):
        errors.add("AI_GATEWAY_EXTRA_HEADERS")
