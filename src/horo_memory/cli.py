from __future__ import annotations

import argparse
import secrets

import uvicorn

from .config import get_settings
from .demo import seed_demo
from .runtime import build_service


def main() -> None:
    parser = argparse.ArgumentParser(prog="horo-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve", help="Run the HORO Memory HTTP service")
    subparsers.add_parser("init", help="Initialize the data directory")
    subparsers.add_parser("token", help="Generate a secure API token")
    demo_parser = subparsers.add_parser("demo", help="Load a safe, simulated commercial demo")
    demo_parser.add_argument("--workspace", default="horo-demo")
    arguments = parser.parse_args()

    if arguments.command == "token":
        print(secrets.token_urlsafe(32))
        return
    settings = get_settings()
    if arguments.command == "init":
        build_service(settings)
        print(f"HORO Memory initialized at {settings.data_dir.resolve()}")
        return
    if arguments.command == "demo":
        result = seed_demo(build_service(settings), arguments.workspace)
        print(f"Demo ready in workspace {result['workspace_id']}")
        return
    if arguments.command == "serve":
        uvicorn.run(
            "horo_memory.api:app",
            host=settings.host,
            port=settings.port,
            proxy_headers=settings.trust_proxy,
            forwarded_allow_ips="127.0.0.1" if settings.trust_proxy else "",
        )


if __name__ == "__main__":
    main()
