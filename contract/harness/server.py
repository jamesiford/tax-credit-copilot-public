"""A server for the replay tool: the real app under a profile, wrapped in the `/__contract__/` control surface, on a real socket.

    python -m contract.harness.server --profile P1 --port 18081

Prints `READY <port>` once the world is built, the app has started and its background start-up checks have settled.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contract.harness import hermetic  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--auth-rate-limit", type=int, default=0, help="serve with Entra sign-in and this per-minute limit (stage C4)")
    args = parser.parse_args()
    hermetic.apply()
    from contract.harness import world

    built = world.build(args.profile)
    if args.auth_rate_limit:
        from contract.harness import auth

        auth.install(args.auth_rate_limit)
    from contract.harness.control import ContractControl

    import uvicorn

    app = ContractControl(built.app)
    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning", lifespan="on", access_log=False)
    server = uvicorn.Server(config)
    original = server.startup

    async def startup(sockets=None):
        await original(sockets)
        print(f"READY {args.port}", flush=True)

    server.startup = startup  # type: ignore[method-assign]
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
