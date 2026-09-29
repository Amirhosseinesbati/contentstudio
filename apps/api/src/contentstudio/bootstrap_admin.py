"""Create the first connected-installation administrator exactly once.

Run after Alembic migrations. The password is read from a terminal or stdin,
never a process argument or environment variable.
"""

import argparse
import getpass
import re
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .auth import hash_password
from .config import get_settings
from .db import session_factory
from .models import InstallationBootstrap, User, Workspace


def validate_details(email: str, slug: str, name: str, password: str) -> None:
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        raise ValueError("Provide a valid administrator email address")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", slug):
        raise ValueError("Workspace slug must use 2–80 lowercase letters, digits, or hyphens")
    if not 2 <= len(name.strip()) <= 150:
        raise ValueError("Workspace name must be 2–150 characters")
    if (
        len(password) < 12
        or len(password) > 128
        or not re.search(r"[a-z]", password)
        or not re.search(r"[A-Z]", password)
        or not re.search(r"\d", password)
        or password == get_settings().demo_password
    ):
        raise ValueError("Use a unique 12–128 character password with upper/lowercase letters and a digit")


def bootstrap(email: str, slug: str, name: str, password: str) -> dict:
    if get_settings().mode != "connected":
        raise RuntimeError("Initial administrator bootstrap requires MODE=connected")
    email = email.lower().strip()
    slug = slug.strip()
    name = name.strip()
    validate_details(email, slug, name, password)
    with session_factory()() as db:
        if db.get(InstallationBootstrap, 1) or db.scalar(select(User.id).limit(1)):
            raise RuntimeError("Installation already contains an account or bootstrap marker")
        workspace = Workspace(slug=slug, name=name)
        try:
            db.add(InstallationBootstrap(id=1))
            db.add(workspace)
            db.flush()
            db.add(
                User(
                    workspace_id=workspace.id,
                    email=email,
                    password_hash=hash_password(password),
                    role="admin",
                    active=True,
                )
            )
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise RuntimeError("Installation was concurrently bootstrapped") from error
    return {"email": email, "workspace_slug": slug}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--workspace-slug", required=True)
    parser.add_argument("--workspace-name", required=True)
    parser.add_argument("--password-stdin", action="store_true", help="Read one password line from stdin without logging it")
    arguments = parser.parse_args()
    if arguments.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        if not sys.stdin.isatty():
            parser.error("An interactive terminal is required unless --password-stdin is set")
        password = getpass.getpass("New administrator password: ")
        if password != getpass.getpass("Repeat password: "):
            parser.error("Passwords do not match")
    try:
        result = bootstrap(
            arguments.email,
            arguments.workspace_slug,
            arguments.workspace_name,
            password,
        )
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(f"Created initial administrator {result['email']} in {result['workspace_slug']}")


if __name__ == "__main__":
    main()
