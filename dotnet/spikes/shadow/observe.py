"""No endpoint, token, SQL or identifier arguments are accepted on a command line."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import logging
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
for name in ("httpx", "httpcore", "azure"):
    client_logger = logging.getLogger(name)
    client_logger.handlers = [logging.NullHandler()]
    client_logger.propagate = False


def main() -> int:
    if sys.argv[1:] != ["--live"]:
        print('{"verdict":"refused","reason":"use-live-with-runtime-environment"}')
        return 2
    try:
        from live import run
        check = os.environ.get("SHADOW_CAPACITY_CHECK")
        if not check:
            result = {"mode": "live", "verdict": "unmeasured", "reason": "capacity-check-runtime-path-missing"}
        else:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = run(Path(check))
    except Exception:  # noqa: BLE001 - terminal privacy boundary, no exception interpolation
        result = {"mode": "live", "verdict": "failed", "reason": "observer-dependency-or-configuration"}
    print(json.dumps(result, indent=2))
    return 0 if result.get("verdict") not in ("failed", "refused") else 2


if __name__ == "__main__":
    raise SystemExit(main())
