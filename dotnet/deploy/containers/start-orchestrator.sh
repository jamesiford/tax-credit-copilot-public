#!/bin/sh
set -eu
# The SDK maps header assertions but cannot authenticate their original subject.
# The preview SDK overrides --urls with ListenAnyIP. A flag is not containment:
# permit proof only in a kernel network namespace containing loopback and nothing else.
if [ "${TCC_ORCHESTRATOR_LOCAL_PROOF:-0}" != "1" ] ||
   [ "${ENVIRONMENT:-}" != "local" ] ||
   [ "${DATA_CLASSIFICATION:-}" != "synthetic" ]; then
    echo "Orchestrator ingress unavailable: verified upstream subject/employer binding required." >&2
    exit 78
fi
set -- /sys/class/net/*
if [ "$#" -ne 1 ] || [ "$1" != "/sys/class/net/lo" ]; then
    echo "Orchestrator proof requires a loopback-only kernel network namespace." >&2
    exit 78
fi
exec dotnet TaxCredit.Orchestrator.dll
