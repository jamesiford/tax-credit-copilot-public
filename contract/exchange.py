"""Execute scenario steps against an `httpx` client and turn each exchange into a recording record.

Shared by the recorder (in-process ASGI transport, or a server it started) and by `replay.py` (any HTTP server), so what is sent and
what is stored cannot diverge between the two.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from typing import Any
from urllib.parse import quote, urlencode

from . import jsontext
from .jsontext import Num

#: Response headers worth recording. Everything else (date, server, content-length, connection...) varies by host, not behaviour.
SELECTED_HEADERS = ("content-type", "content-disposition", "retry-after", "cache-control", "www-authenticate", "location", "allow", "vary")
_VAR = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}")


class ScenarioError(RuntimeError):
    pass


def selected_headers(headers: Any) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    for key, value in headers.multi_items():
        name = key.lower()
        if name in SELECTED_HEADERS or name.startswith("x-") or name.startswith("access-control-"):
            out.setdefault(name, []).append(value)
    return {k: ", ".join(v) for k, v in sorted(out.items())}


def lookup(tree: Any, path: str) -> Any:
    """`a.b.0.c` over dicts and lists; a missing step raises, so a scenario cannot silently capture nothing."""
    node = tree
    for part in path.split("."):
        if isinstance(node, list):
            node = node[int(part)]
        elif isinstance(node, dict):
            node = node[part]
        else:
            raise KeyError(path)
    return node


def substitute(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        whole = _VAR.fullmatch(value.strip())
        if whole and value == value.strip():
            return _var(whole.group(1), variables)
        return _VAR.sub(lambda m: str(_var(m.group(1), variables)), value)
    if isinstance(value, dict):
        return {substitute(k, variables): substitute(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, variables) for v in value]
    return value


def _var(name: str, variables: dict[str, Any]) -> Any:
    if name not in variables:
        raise ScenarioError(f"scenario variable {name!r} was never captured")
    return variables[name]


def _query(step_request: dict[str, Any], variables: dict[str, Any]) -> str:
    if "raw_query" in step_request:
        return str(substitute(step_request["raw_query"], variables))
    query = substitute(step_request.get("query") or [], variables)
    pairs = list(query.items()) if isinstance(query, dict) else [tuple(p) for p in query]
    return urlencode([(k, "" if v is None else v) for k, v in pairs], quote_via=quote)


def build_request(step_request: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """What goes on the wire, and the record of it."""
    method = step_request["method"].upper()
    path = substitute(step_request["path"], variables)
    query = _query(step_request, variables)
    headers = {k: str(v) for k, v in substitute(step_request.get("headers") or {}, variables).items()}
    content: bytes | None = None
    body_record: dict[str, Any] = {"kind": "none"}
    if "json" in step_request:
        value = substitute(step_request["json"], variables)
        content = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        body_record = {"kind": "json", "value": value}
        headers.setdefault("content-type", "application/json")
    elif "body_text" in step_request:
        text = substitute(step_request["body_text"], variables)
        content = text.encode("utf-8")
        body_record = {"kind": "text", "text": text}
    elif "body_b64" in step_request:
        content = base64.b64decode(step_request["body_b64"])
        body_record = {"kind": "bytes", "length": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    elif "form" in step_request:
        form = substitute(step_request["form"], variables)
        content = urlencode(form, quote_via=quote).encode()
        body_record = {"kind": "form", "value": form}
        headers.setdefault("content-type", "application/x-www-form-urlencoded")
    return {
        "wire": {"method": method, "url": path + (f"?{query}" if query else ""), "headers": headers, "content": content},
        "record": {"method": method, "path": path, "query": query, "headers": dict(sorted((k.lower(), v) for k, v in headers.items())), "body": body_record},
    }


def _sse_events(text: str) -> list[dict[str, Any]]:
    events = []
    for frame in re.split(r"\r?\n\r?\n", text):
        if not frame.strip():
            continue
        event: dict[str, Any] = {}
        data: list[str] = []
        for line in re.split(r"\r?\n", frame):
            if line.startswith(":"):
                event.setdefault("comments", []).append(line[1:].lstrip())
                continue
            name, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if name == "data":
                data.append(value)
            else:
                event[name] = value
        joined = "\n".join(data)
        try:
            event["data"] = jsontext.loads(joined) if data else None
        except ValueError:
            event["data"] = joined
        events.append(event)
    return events


def describe_body(headers: Any, content: bytes) -> dict[str, Any]:
    sha, length = hashlib.sha256(content).hexdigest(), len(content)
    ctype = (headers.get("content-type") or "").lower()
    if not content:
        return {"kind": "empty"}
    if "event-stream" in ctype:
        text = content.decode("utf-8")
        return {"kind": "sse", "events": _sse_events(text), "raw_sha256": sha, "raw_length": length}
    if "json" in ctype:
        try:
            tree = jsontext.loads(content)
            return {"kind": "json", "value": tree, "raw_sha256": sha, "raw_length": length, "ascii_only": all(b < 128 for b in content)}
        except (ValueError, UnicodeDecodeError) as exc:
            return {"kind": "text", "text": content.decode("utf-8", "replace"), "invalid_json": type(exc).__name__, "raw_sha256": sha, "raw_length": length}
    if ctype.startswith("text/") or ctype.split(";")[0].strip() in ("application/xml",) or ctype.split(";")[0].strip().endswith("+xml"):
        text = content.decode("utf-8", "replace")
        record: dict[str, Any] = {"kind": "text", "raw_sha256": sha, "raw_length": length}
        record["text"] = text if length <= 4096 else None
        return record
    record = {"kind": "bytes", "length": length, "sha256": sha}
    if content[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                record["zip_entries"] = [{"name": i.filename, "size": i.file_size, "sha256": hashlib.sha256(z.read(i)).hexdigest()} for i in z.infolist()]
        except zipfile.BadZipFile:
            pass
    return record


async def run_step(http: Any, step: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    built = build_request(step["request"], variables)
    wire = built["wire"]
    response = await http.request(wire["method"], wire["url"], headers=wire["headers"], content=wire["content"])
    body = describe_body(response.headers, response.content)
    record = {"id": step["id"], "note": step.get("note", ""), "request": built["record"],
              "response": {"status": response.status_code, "headers": selected_headers(response.headers), "body": body}}
    for name, path in (step.get("capture") or {}).items():
        try:
            source = body.get("value") if path.startswith("body.") or path == "body" else response.headers
            if path.startswith("header."):
                variables[name] = response.headers[path[len("header."):]]
            else:
                variables[name] = jsontext.to_plain(lookup(source, path[len("body."):])) if path != "body" else jsontext.to_plain(source)
        except (KeyError, IndexError, TypeError):
            variables.setdefault(name, "capture-failed")
            record.setdefault("capture_failed", []).append(name)
    return record


async def run_control(http: Any, step: dict[str, Any]) -> dict[str, Any]:
    control = step["control"]
    path = {"drain": "/__contract__/drain", "env": "/__contract__/env", "reset": "/__contract__/reset"}[control["op"]]
    response = await http.post(path, content=json.dumps(control.get("args") or {}).encode(), headers={"content-type": "application/json"})
    return {"id": step["id"], "note": step.get("note", ""), "control": {"op": control["op"], "args": control.get("args") or {}, "status": response.status_code}}


async def run_scenario(http: Any, scenario: dict[str, Any]) -> list[dict[str, Any]]:
    variables: dict[str, Any] = dict(scenario.get("variables") or {})
    out: list[dict[str, Any]] = []
    for index, step in enumerate(scenario["steps"]):
        started = time.time()
        record = await (run_control(http, step) if "control" in step else run_step(http, step, variables))
        record["scenario"], record["step"], record["profile"] = scenario["name"], index, scenario["profile"]
        out.append(record)
        if os.environ.get("CONTRACT_PROGRESS") or time.time() - started > 20:
            print(f"[{index + 1}/{len(scenario['steps'])}] {step['id']} {time.time() - started:.1f}s", file=sys.stderr, flush=True)
    return out


def dump_record(record: dict[str, Any]) -> str:
    """One recording line: valid JSON, number lexemes and key order exactly as observed."""
    return jsontext.dumps(record)


def load_records(text: str) -> list[dict[str, Any]]:
    return [jsontext.loads(line) for line in text.splitlines() if line.strip()]
