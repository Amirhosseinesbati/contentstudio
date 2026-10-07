"""Export the exact FastAPI schema used to generate the typed web client."""

import json
from pathlib import Path

from .main import app


def main():
    destination = Path("openapi.json")
    destination.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8", newline="\n")
    print(destination.resolve())


if __name__ == "__main__":
    main()
