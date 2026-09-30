"""Block every outbound network connection from the worker process.

Installed at interpreter start-up by worker/sitecustomize.py (set
OTK_NETGUARD=0 to disable, e.g. for debugging). Loopback and AF_UNIX stay
allowed: Windows builds socketpair() on 127.0.0.1, and that is not network
traffic. Every blocked attempt is recorded and logged to stderr as
`OFFLINE_VIOLATION {...}` so the offline self-test can count them.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import sys
import threading
import traceback

_installed = False
_lock = threading.Lock()
violations: list[dict] = []

_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", ""}


class OfflineViolation(ConnectionRefusedError):
    """Raised instead of opening a network connection."""


def _is_loopback(host) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").lower()
    if host in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _record(kind: str, target) -> None:
    entry = {"kind": kind, "target": repr(target), "stack": traceback.format_stack(limit=6)[:-2]}
    with _lock:
        violations.append(entry)
    try:
        sys.stderr.write("OFFLINE_VIOLATION " + json.dumps({"kind": kind, "target": repr(target)}) + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _address_host(address):
    if isinstance(address, tuple) and address:
        return address[0]
    return None


def install() -> None:
    global _installed
    if _installed:
        return
    _installed = True
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_sendto = socket.socket.sendto
    real_getaddrinfo = socket.getaddrinfo

    def _guard(sock, address, kind):
        if sock.family == getattr(socket, "AF_UNIX", object()):
            return
        host = _address_host(address)
        if not _is_loopback(host):
            _record(kind, address)
            raise OfflineViolation(f"Offline Toolkit blocks network access ({kind} to {address!r})")

    def connect(self, address):
        _guard(self, address, "connect")
        return real_connect(self, address)

    def connect_ex(self, address):
        _guard(self, address, "connect")
        return real_connect_ex(self, address)

    def sendto(self, data, *args):
        address = args[-1] if args else None
        _guard(self, address, "sendto")
        return real_sendto(self, data, *args)

    def getaddrinfo(host, *args, **kwargs):
        if not _is_loopback(host):
            _record("dns", host)
            raise socket.gaierror(socket.EAI_NONAME, f"Offline Toolkit blocks DNS lookups ({host!r})")
        return real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.getaddrinfo = getaddrinfo


def canary() -> dict:
    """Try to reach a public host; report whether the guard stopped it (self-test)."""
    before = len(violations)
    blocked = False
    error = None
    try:
        socket.create_connection(("example.com", 443), timeout=2).close()
    except OfflineViolation as exc:
        blocked, error = True, str(exc)
    except socket.gaierror as exc:
        blocked, error = "Offline Toolkit" in str(exc), str(exc)
    except OSError as exc:
        error = str(exc)
    return {"blocked": blocked, "error": error, "recorded": len(violations) - before, "installed": _installed}
