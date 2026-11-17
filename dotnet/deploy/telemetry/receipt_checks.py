"""Assert real receipt and loss behavior rather than successful configuration."""

import http.server
import json
import threading
import time

import probe_support as s


def records(payloads, kind):
    for payload in payloads:
        for resource in payload.get("resource" + kind, []):
            attrs = {item["key"]: item["value"]["stringValue"]
                     for item in resource["resource"]["attributes"]}
            assert set(attrs) == {"service.name", "service.version"}
            assert attrs["service.version"] == s.VERSION
            for scope in resource["scope" + kind]:
                for value in scope[kind.lower()]:
                    yield attrs["service.name"], value


def assert_privacy(payloads):
    encoded = json.dumps(payloads)
    assert s.POISON not in encoded
    for forbidden in ("url.", "http.route", "person.", "gen_ai.prompt", "exception.",
                      "authorization", "private.person", "Unapproved.Secret", "traceState",
                      "baggage", "events", "links", "statusMessage"):
        assert forbidden not in encoded, "Non-allowlisted telemetry escaped"
    spans = list(records(payloads, "Spans"))
    allowed = {"traceId", "spanId", "parentSpanId", "name", "kind", "startTimeUnixNano",
               "endTimeUnixNano", "status", "flags"}
    for _, span in spans:
        assert set(span) <= allowed, "Unexpected span field"
        assert set(span.get("status", {})) <= {"code"}
        assert span["name"].split(".")[-1] in {"Server", "Client", "Internal"}
    for _, metric in records(payloads, "Metrics"):
        assert set(metric) <= {"name", "histogram", "metadata"}
        assert metric["name"].startswith("tcc.deployment.measurement.")
        histogram = metric["histogram"]
        assert histogram["aggregationTemporality"] in (1, "AGGREGATION_TEMPORALITY_DELTA")
        for point in histogram["dataPoints"]:
            assert not point.get("attributes") and not point.get("exemplars")
            assert set(point) <= {"startTimeUnixNano", "timeUnixNano", "count", "sum",
                                  "bucketCounts", "explicitBounds", "flags"}
    return spans


def assert_services(spans, metrics):
    for service in ("taxcredit-api", "taxcredit-gateway", "taxcredit-worker"):
        assert any(owner == service and value["name"] == "TaxCredit.Ai.Client" for owner, value in spans)
        for suffix in ("ai.retries", "http.server.request.duration",
                       "gen_ai.client.operation.duration", "gen_ai.client.token.usage"):
            assert any(owner == service and value["name"].endswith(suffix) for owner, value in metrics)
        retry_sum = sum(point["sum"] for owner, metric in metrics
                        if owner == service and metric["name"].endswith("ai.retries")
                        for point in metric["histogram"]["dataPoints"])
        assert retry_sum == 1, "Unregistered meter was exported"


def assert_chain():
    spans = assert_privacy(s.snapshot())
    assert_services(spans, list(records(s.snapshot(), "Metrics")))
    by_id = {span["spanId"]: (service, span) for service, span in spans}
    assert sum(span["name"] == "System.Net.Http.Client" for _, span in spans) == 2, (
        "Exporter HTTP calls must not recursively generate exported telemetry")
    correlations = 0
    for service, span in spans:
        if span["name"] != "Microsoft.AspNetCore.Server":
            continue
        parent = by_id.get(span.get("parentSpanId"))
        if parent and parent[1]["name"] == "System.Net.Http.Client":
            assert parent[1]["traceId"] == span["traceId"]
            assert parent[0] != service
            correlations += 1
    assert correlations == 2, "API/gateway/dependency W3C parentage was not preserved"
    return correlations


def exercise_chain(endpoint, receipt_wait):
    with s.owned_processes() as processes:
        dependency = s.start_host(endpoint, "taxcredit-worker")
        processes.append(dependency)
        gateway = s.start_host(endpoint, "taxcredit-gateway", dependency[1])
        processes.append(gateway)
        api = s.start_host(endpoint, "taxcredit-api", gateway[1])
        processes.append(api)
        assert s.subscriptions(api[1]) == {"custom_trace": True, "custom_meter": True}
        assert s.request(api[1] + "/" + s.POISON + "?private=" + s.POISON) == 200
        latencies = [s.stop_host(*host) for host in reversed(processes)]
        for process, _ in processes:
            s.assert_diagnostics(process, [])
        processes.clear()
    time.sleep(receipt_wait)
    return latencies, assert_chain()


def check_flush(endpoint, receipt_wait):
    before = len(list(records(s.snapshot(), "Spans")))
    started = time.monotonic()
    with s.owned_processes() as processes:
        host = s.start_host(endpoint, "taxcredit-orchestrator")
        processes.append(host)
        assert s.request(host[1] + "/" + s.POISON) == 200
        shutdown = s.stop_host(*host)
        s.assert_diagnostics(host[0], [])
        processes.clear()
    elapsed = round(time.monotonic() - started, 3)
    assert elapsed < 2, "Immediate flush proof must precede the periodic timer"
    time.sleep(receipt_wait)
    assert len(list(records(s.snapshot(), "Spans"))) > before
    assert any(owner == "taxcredit-orchestrator" and value["name"] == "TaxCredit.Ai.Client"
               for owner, value in records(s.snapshot(), "Spans"))
    return shutdown, elapsed


def check_refused():
    with s.owned_processes() as processes:
        host = s.start_host(f"http://127.0.0.1:{s.port()}/", "taxcredit-api")
        processes.append(host)
        assert s.request(host[1] + "/" + s.POISON) == 200
        shutdown = s.stop_host(*host)
        s.assert_diagnostics(host[0], ["TCC_TELEMETRY_EXPORT_FAILED"])
        processes.clear()
    return shutdown


def check_disabled(endpoint, receipt_wait):
    checks = 0
    for options in ({"enabled": "0"}, {"enabled": s.POISON}, {"version": s.POISON}, {"service": s.POISON},
                    {"endpoint": "http://example.invalid/"}, {"endpoint": endpoint + "?token=bad"}):
        before_count = len(s.snapshot())
        config = dict(endpoint=endpoint, service="taxcredit-api")
        config.update(options)
        with s.owned_processes() as processes:
            host = s.start_host(**config)
            processes.append(host)
            assert s.subscriptions(host[1]) == {"custom_trace": False, "custom_meter": False}
            assert s.request(host[1] + "/" + s.POISON) == 200
            s.stop_host(*host)
            expected = [] if options.get("enabled") == "0" else ["TCC_TELEMETRY_INVALID_CONFIGURATION"]
            s.assert_diagnostics(host[0], expected)
            processes.clear()
        time.sleep(receipt_wait)
        assert len(s.snapshot()) == before_count
        checks += 1
    return checks


def failed_receivers():
    if s.LINUX_CONTAINER:
        return {}
    results = {}
    for failure in ("http_503", "timeout", "partial_success", "malformed_response"):
        receiver = http.server.ThreadingHTTPServer(("127.0.0.1", 0), s.UnavailableReceiver)
        receiver.failure = failure
        threading.Thread(target=receiver.serve_forever, daemon=True).start()
        try:
            with s.owned_processes() as processes:
                host = s.start_host(f"http://127.0.0.1:{receiver.server_port}/", "taxcredit-api")
                processes.append(host)
                started = time.monotonic()
                assert s.request(host[1] + "/" + s.POISON) == 200
                latency = round(time.monotonic() - started, 3)
                shutdown = s.stop_host(*host)
                s.assert_diagnostics(host[0], ["TCC_TELEMETRY_EXPORT_FAILED"])
                processes.clear()
                assert shutdown < 4
                results[failure] = {
                    "request_seconds": latency, "shutdown_seconds": shutdown, "exit_code": 0,
                    "fixed_diagnostic_once": True}
        finally:
            receiver.shutdown()
            receiver.server_close()
    return results


def verify(endpoint, receipt_wait):
    started = time.monotonic()
    latencies, correlations = exercise_chain(endpoint, receipt_wait)
    flush_time, elapsed = check_flush(endpoint, receipt_wait)
    outage_shutdown = check_refused()
    disabled_checks = check_disabled(endpoint, receipt_wait)
    assert_privacy(s.snapshot())
    return {
        "receipt_payloads": len(s.snapshot()),
        "trace_spans": len(list(records(s.snapshot(), "Spans"))),
        "metric_series_batches": len(list(records(s.snapshot(), "Metrics"))),
        "cross_service_parent_edges": correlations,
        "service_version_attributions": 4,
        "shutdown_seconds": latencies,
        "immediate_flush_shutdown_seconds": flush_time,
        "immediate_flush_process_seconds": elapsed,
        "collector_refused_shutdown_seconds": outage_shutdown,
        "disabled_or_invalid_configuration_checks": disabled_checks,
        "custom_source_and_meter_with_hook": True,
        "custom_source_and_meter_without_hook": False,
        "privacy_allowlist": "passed",
        "fixed_diagnostics_checked": not bool(s.LINUX_CONTAINER),
        "duration_seconds": round(time.monotonic() - started, 3),
        "additional_collector_failures": failed_receivers(),
    }
