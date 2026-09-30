"""Imported automatically by Python at start-up because worker/ is on PYTHONPATH.

Installs the network guard before any library can open a connection.
"""

import os

if os.environ.get("OTK_NETGUARD", "1") != "0":
    try:
        from otk_worker import netguard

        netguard.install()
    except Exception as exc:  # never stop the worker from starting; the self-test will flag it
        import sys

        sys.stderr.write(f"OFFLINE_GUARD_FAILED {exc!r}\n")
