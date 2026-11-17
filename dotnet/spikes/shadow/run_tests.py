"""Safe test launcher: even a failing privacy assertion cannot print the sentinel or a traceback."""
import io
import json
from pathlib import Path
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            suite = unittest.defaultTestLoader.discover(str(HERE), pattern="test_*.py")
            result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        output = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "passed": result.wasSuccessful()}
    except Exception:  # noqa: BLE001 - intentionally no unsafe exception text at this output boundary
        output = {"tests": 0, "failures": 0, "errors": 1, "skipped": 0, "passed": False}
    print(json.dumps(output))
    return int(not output["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
