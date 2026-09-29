"""Small local login throttle to bound Argon2 work per peer and account."""

import hashlib
import threading
import time
from collections import OrderedDict

WINDOW_SECONDS = 60
MAX_PEER_FAILURES = 20
MAX_ACCOUNT_FAILURES = 5
MAX_BUCKETS = 4096

_lock = threading.Lock()
_failures: OrderedDict[str, list[float]] = OrderedDict()


def _keys(peer: str, email: str) -> tuple[str, str]:
    account = hashlib.sha256(email.lower().strip().encode("utf-8")).hexdigest()
    return f"peer:{peer}", f"account:{account}"


def _recent(key: str, current: float) -> list[float]:
    recent = [at for at in _failures.get(key, []) if current - at < WINDOW_SECONDS]
    if recent:
        _failures[key] = recent
        _failures.move_to_end(key)
    else:
        _failures.pop(key, None)
    return recent


def login_allowed(peer: str, email: str) -> bool:
    current = time.monotonic()
    peer_key, account_key = _keys(peer, email)
    with _lock:
        return (
            len(_recent(peer_key, current)) < MAX_PEER_FAILURES
            and len(_recent(account_key, current)) < MAX_ACCOUNT_FAILURES
        )


def login_failed(peer: str, email: str) -> None:
    current = time.monotonic()
    with _lock:
        for key in _keys(peer, email):
            recent = _recent(key, current)
            _failures[key] = [*recent, current]
            _failures.move_to_end(key)
        while len(_failures) > MAX_BUCKETS:
            _failures.popitem(last=False)


def login_succeeded(peer: str, email: str) -> None:
    with _lock:
        _failures.pop(_keys(peer, email)[1], None)
