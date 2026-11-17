"""Expand the reviewed inventory without manufacturing support from Python names."""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICES = ("api", "worker", "gateway", "orchestrator")


def inventory():
    """Return one complete record per setting, including absent service consumers."""
    document = json.loads((HERE / "inventory.json").read_text(encoding="utf-8"))
    records = {}
    grouped = {"names", "defaults", "targets", "required_by_name", "consumer_names", "unsupported_consumers"}
    for group in document["groups"]:
        for name in group["names"]:
            if name in records:
                raise ValueError("Duplicate inventory name")
            record = {key: value for key, value in group.items() if key not in grouped}
            record["name"] = name
            for plural, singular in (("defaults", "default"), ("targets", "target"),
                                     ("required_by_name", "required")):
                if name in group.get(plural, {}):
                    record[singular] = group[plural][name]
            scopes = group.get("consumer_names", {})
            record["consumers"] = {
                service: consumer
                for service, consumer in group["consumers"].items()
                if service not in scopes or name in scopes[service]
            }
            record["service_scope"] = sorted(record["consumers"])
            record["per_service"] = {
                service: {
                    "classification": classification(group, name, service)
                        if service in record["consumers"] else "irrelevant",
                    "consumer": record["consumers"].get(service, "absent"),
                    "unset": record["unset"] if service in record["consumers"] else "ignored",
                    "empty": record["empty"] if service in record["consumers"] else "ignored",
                }
                for service in SERVICES
            }
            records[name] = record
    return records


def classification(group, name, service):
    if name in group.get("unsupported_consumers", {}).get(service, []):
        return "unsupported"
    return group.get("overrides", {}).get(service, group["classification"])


def documented_names(path):
    """Include every literal environment/input/output name, not just runtime rows."""
    text = Path(path).read_text(encoding="utf-8")
    pattern = r"(?<![a-zA-Z0-9_])(?:[A-Z][A-Z0-9]*_+[A-Z0-9_]+|ENVIRONMENT|PORT)(?![a-zA-Z0-9_])"
    names = {
        name for token in re.findall(r"`([^`]+)`", text)
        for name in re.findall(pattern, token) if not name.endswith("_")
    } | {"PYTHONNOUSERSITE"}
    return names | set(re.findall(r"`(TF_VAR_[A-Za-z0-9_]+)`", text))
