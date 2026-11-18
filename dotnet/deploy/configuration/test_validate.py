"""Hermetic configuration proofs: synthetic manifests only, no credential acquisition."""

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

from contract import HERE, SERVICES, documented_names, inventory
from validate import main, validate

ROOT = HERE.parents[2]


def example(service):
    return json.loads((HERE / "examples" / (service + ".json")).read_text(encoding="utf-8"))


class ConfigurationTests(unittest.TestCase):
    def test_examples_are_synthetic_and_validate_without_network(self):
        for service in SERVICES:
            with self.subTest(service=service):
                self.assertEqual([], validate(example(service), service))

    def test_inventory_covers_every_documented_input_output_and_old_name(self):
        records = inventory()
        self.assertFalse(documented_names(ROOT / "docs" / "architecture" / "ENV-VARS.md") - records.keys())
        required = {"classification", "source", "consumers", "required", "unset", "empty",
                    "per_service", "service_scope"}
        for record in records.values():
            with self.subTest(name=record["name"]):
                self.assertFalse(required - record.keys())
                self.assertEqual(set(SERVICES), set(record["per_service"]))

    def test_missing_and_empty_required_settings_are_names_only(self):
        for service, name in (("api", "FABRIC_SQL_SERVER"), ("api", "AUTH_TENANT_ID"),
                              ("gateway", "GATEWAY_AUDIENCE"),
                              ("orchestrator", "CHANNEL_GATEWAY_AUDIENCE")):
            for value in (None, ""):
                data = example(service)
                if value is None:
                    del data[name]
                else:
                    data[name] = value
                with self.subTest(service=service, name=name, value=value):
                    self.assertIn(name, validate(data, service))

    def test_schema_unset_empty_and_whitespace_are_intentionally_distinct(self):
        for schema in (None, "", "   ", "tcc_source", "source-schema", "0schema"):
            data = example("api")
            if schema is None:
                del data["SOURCE_SCHEMA"]
            else:
                data["SOURCE_SCHEMA"] = schema
            self.assertEqual([], validate(data, "api"))
        data["SOURCE_SCHEMA"] = "bad.schema"
        self.assertIn("SOURCE_SCHEMA", validate(data, "api"))

    def test_malformed_and_runtime_specific_booleans(self):
        for service, name, value in (
                ("api", "CHANNEL_ENFORCE_WRITER_FOR_USERS", "on"),
                ("api", "CHANNEL_ENFORCE_WRITER_FOR_USERS", "sometimes"),
                ("gateway", "CHANNEL_DEBUG_WHOAMI", "occasionally"),
                ("orchestrator", "AI_GATEWAY_STREAMING", "sometimes"),
                ("orchestrator", "AI_GATEWAY_SUPPORTS_TOOLS", "sometimes"),
                ("orchestrator", "KNOWLEDGE_ENABLED", "sometimes")):
            data = example(service)
            data[name] = value
            with self.subTest(service=service, name=name):
                self.assertIn(name, validate(data, service))

    def test_malformed_audiences_and_urls(self):
        for service, name, values in (
                ("api", "API_AUDIENCE", ["", "not-an-audience", "https://wrong.example.invalid"]),
                ("orchestrator", "CHANNEL_GATEWAY_AUDIENCE", ["http://wrong.example.invalid"]),
                ("orchestrator", "CHANNEL_GATEWAY_URL",
                 ["http://gateway.example.invalid", "https://synthetic-user@gateway.example.invalid",
                  "https://bad..example.invalid", "https://bad%host.example.invalid",
                  "https://gateway.example.invalid?credential=redacted", "https://gateway.example.invalid/#fragment"]),
                ("orchestrator", "AI_GATEWAY_ENDPOINT", ["https://model.example.invalid/path"]),
                ("api", "ARTIFACT_BLOB_ACCOUNT_URL", ["https://blob.example.invalid/container"])):
            for value in values:
                data = example(service)
                data[name] = value
                with self.subTest(service=service, name=name):
                    self.assertIn(name, validate(data, service))

    def test_legacy_and_unsupported_controls_cannot_masquerade_as_working(self):
        names = ("WAREHOUSE_SERVER", "LAKEHOUSE_SQL_SERVER", "SOURCE_MAPPING_FILE",
                 "SOURCE_TABLE_PREFIX", "DATA_MIN_GROUP_SIZE", "RUN_LEASE_SECONDS",
                 "RUN_HEARTBEAT_SECONDS", "RUN_WORKER_POLL_SECONDS", "AI_GATEWAY_TLS_VERIFY")
        for name in names:
            data = example("api")
            data[name] = "synthetic"
            self.assertEqual([name], validate(data, "api"))

    def test_deployed_local_stores_and_replay_features_are_refused(self):
        for name, value in (("PERSISTENCE_PROVIDER", "sqlite"),
                            ("PERSISTENCE_PROVIDER", "memory"), ("DATA_SOURCE", "csv"),
                            ("ARTIFACT_STORE", "local"), ("AUTH_MODE", "none"),
                            ("CONTRACT_HOOKS", "1"), ("ALLOW_ANONYMOUS_SYNTHETIC", "1"),
                            ("FEATURE_ASSEMBLIES", "untrusted"),
                            ("CLAIM_STORE", "memory"), ("OPERATIONAL_DB", "local.db")):
            data = example("api")
            data[name] = value
            self.assertIn(name, validate(data, "api"))

    def test_signed_access_requires_client_binding_and_writer_policy(self):
        for name, value in (("CLIENT_ALLOWLIST", "{}"), ("CLIENT_ALLOWLIST", "[]"),
                            ("CHANNEL_WRITER_SOURCE", "entra_group"),
                            ("CHANNEL_ENFORCE_WRITER_FOR_USERS", "false")):
            data = example("api")
            data[name] = value
            expected = "CHANNEL_WRITER_GROUP_ID" if name == "CHANNEL_WRITER_SOURCE" else name
            self.assertIn(expected, validate(data, "api"))

    def test_gateway_privacy_posture_and_tenant_audience_separation(self):
        data = example("gateway")
        self.assertNotEqual(data["API_AUDIENCE"], data["GATEWAY_AUDIENCE"])
        data["TENANT_ID"] = "00000000-0000-0000-0000-000000000099"
        self.assertIn("TENANT_ID", validate(data, "gateway"))
        for name, value in (("CHANNEL_MCP_ALLOWED_ORIGINS", "*"),
                            ("CHANNEL_CALLER_CHANNELS", "not-guid=teams"),
                            ("CHANNEL_RATE_LIMIT_PER_MINUTE", "6001"),
                            ("CHANNEL_DEBUG_WHOAMI", "true")):
            data = example("gateway")
            data[name] = value
            self.assertIn(name, validate(data, "gateway"))

class ModelAndPrivacyTests(unittest.TestCase):
    def test_orchestrator_url_override_is_not_a_supported_confinement_control(self):
        record = inventory()["ASPNETCORE_URLS"]
        self.assertEqual("unsupported", record["per_service"]["orchestrator"]["classification"])
        data = example("orchestrator")
        data["ASPNETCORE_URLS"] = "http://127.0.0.1:8088"
        self.assertEqual(["ASPNETCORE_URLS"], validate(data, "orchestrator"))

    def test_models_refuse_unsafe_controls_and_unavailable_providers(self):
        for name, value in (("AI_GATEWAY_TLS_VERIFY", "false"),
                            ("AI_GATEWAY_AUTH", "none"), ("AI_INJECTION_GUARD", "off"),
                            ("AI_OUTPUT_POLICY", "off"), ("AI_EGRESS_POLICY", "allow_all"),
                            ("AI_TOKEN_BUDGET_DAILY", "-1"), ("AI_CALL_TIMEOUT_SECONDS", "nan"),
                            ("AI_RETRY_MAX_ATTEMPTS", "1.5"), ("AI_PROVIDER_CHAIN", "foundry_connection"),
                            ("KNOWLEDGE_ENABLED", "true"),
                            ("CHANNEL_IDENTITY_SOURCES", "client-headers"),
                            ("AI_GATEWAY_EXTRA_HEADERS", '{"x-safe":"bad\\r\\nheader"}')):
            data = example("orchestrator")
            data[name] = value
            self.assertIn(name, validate(data, "orchestrator"))

    def test_each_gateway_role_requires_a_model_and_overrides_are_honored(self):
        data = example("orchestrator")
        del data["AI_MODEL_NARRATOR"]
        self.assertIn("AI_MODEL_NARRATOR__GATEWAY", validate(data, "orchestrator"))
        data["AI_MODEL_NARRATOR__GATEWAY"] = "synthetic-override"
        self.assertEqual([], validate(data, "orchestrator"))

    def test_input_contents_never_appear_in_diagnostics(self):
        marker = "SYNTHETIC-DIAGNOSTIC-CONTENTS-MUST-NOT-APPEAR"
        data = example("api")
        data["API_AUDIENCE"] = marker
        errors = validate(data, "api")
        self.assertNotIn(marker, json.dumps(errors))
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(["--service", "api", "--file", str(HERE / "absent.json")])
        self.assertEqual(1, result)
        self.assertEqual({"valid": False, "settings": ["configuration"]}, json.loads(output.getvalue()))

    def test_missing_resource_package_has_only_setting_name_diagnostic(self):
        data = example("api")
        data["REPOSITORY_ROOT"] = str(HERE / "absent-resources")
        self.assertIn("REPOSITORY_ROOT", validate(data, "api", check_resources=True))

    def test_platform_and_logging_controls_are_not_arbitrary_strings(self):
        for name, value in (("SCM_DO_BUILD_DURING_DEPLOYMENT", "sometimes"),
                            ("WEBSITE_RUN_FROM_PACKAGE", "https://package.example.invalid"),
                            ("ASPNETCORE_ENVIRONMENT", ""),
                            ("Logging__LogLevel__Default", "Trace")):
            data = example("api")
            data[name] = value
            self.assertIn(name, validate(data, "api"))

    def test_oauth_missing_controls_and_forbidden_secret_emission_are_value_free(self):
        data = example("orchestrator")
        data["AI_GATEWAY_AUTH"] = "oauth_client_credentials"
        errors = validate(data, "orchestrator")
        for name in ("AI_GATEWAY_AUTH", "AI_GATEWAY_OAUTH_TOKEN_URL",
                     "AI_GATEWAY_OAUTH_CLIENT_ID", "AI_GATEWAY_OAUTH_CLIENT_SECRET"):
            self.assertIn(name, errors)
        data = example("orchestrator")
        data["AI_GATEWAY_API_KEY"] = ""
        self.assertIn("AI_GATEWAY_API_KEY", validate(data, "orchestrator"))

    def test_selected_actual_consumer_expressions_are_verified(self):
        folder = ROOT / "dotnet" / "src" / "TaxCredit.ServiceDefaults" / "Hosting"
        source = (folder / "RuntimeSourceRegistration.cs").read_text(encoding="utf-8")
        self.assertIn('SourceMapping.Load()', source)
        self.assertIn('settings.Get("SOURCE_SCHEMA") ?? "tcc_source"', source)
        paths = (folder / "RuntimePaths.cs").read_text(encoding="utf-8")
        self.assertIn('settings.Get("REPOSITORY_ROOT") ?? Discover()', paths)
        self.assertNotIn("RESOURCE_ROOT", paths)
        scanner = (ROOT / "dotnet" / "src" / "TaxCredit.Infrastructure.Sources" /
                   "Sql" / "SourceScanner.cs").read_text(encoding="utf-8")
        self.assertIn('Schema.Length == 0 ? "dbo" : Schema', scanner)


if __name__ == "__main__":
    unittest.main()
