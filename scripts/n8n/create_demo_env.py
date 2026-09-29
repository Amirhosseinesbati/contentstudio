"""Create a private DEMO .env with fresh secrets without printing them."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n8n-port", type=int, default=5678)
    parser.add_argument("--sim-port", type=int, default=8081)
    args = parser.parse_args()
    for port in (args.n8n_port, args.sim_port):
        if not 1 <= port <= 65535:
            parser.error("Ports must be between 1 and 65535")
    if args.n8n_port == args.sim_port:
        parser.error("n8n and simulator host ports must differ")

    replacements = {
        "POSTGRES_PASSWORD": secrets.token_hex(32),
        "SERVICE_TOKEN": secrets.token_hex(32),
        "N8N_ENCRYPTION_KEY": secrets.token_hex(32),
        "SIM_WORDPRESS_PASSWORD": secrets.token_hex(32),
        "SIM_CONTROL_TOKEN": secrets.token_hex(32),
        "DEMO_PASSWORD": secrets.token_urlsafe(20),
        "N8N_PUBLIC_URL": f"http://localhost:{args.n8n_port}",
        "N8N_WEBHOOK_URL": f"http://localhost:{args.n8n_port}/",
        "N8N_HOST_PORT": str(args.n8n_port),
        "SIM_HOST_PORT": str(args.sim_port),
        "N8N_SAVE_SUCCESS_EXECUTIONS": "all",
    }
    source = (ROOT / ".env.example").read_text(encoding="utf-8")
    lines = []
    for line in source.splitlines():
        key = line.split("=", 1)[0]
        lines.append(f"{key}={replacements[key]}" if key in replacements else line)
    target = ROOT / ".env"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")
    print(f"Created private {target.name} with fresh DEMO secrets and loopback ports")


if __name__ == "__main__":
    main()
