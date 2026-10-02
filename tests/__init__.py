"""Council v2 test-suite.  Runs offline, with no API keys.

Importing this package installs a guard that makes every outbound socket
connection raise, so a test that accidentally reaches a provider fails
instead of spending money.  Local subprocesses (git, the executor's scenario
runs) are unaffected.
"""

import os
import socket

_real_connect = socket.socket.connect


class NetworkBlocked(RuntimeError):
    pass


def _blocked(self, address, *args, **kwargs):  # pragma: no cover - only hit on a bug
    raise NetworkBlocked(f"network access attempted during tests: {address!r}")


socket.socket.connect = _blocked
socket.create_connection = lambda *a, **k: _blocked(None, a)  # type: ignore[assignment]

# Never inherit a live switch or real keys from the developer's shell.
for _k in ("AETHERNEUM_COUNCIL_LIVE", "ANTHROPIC_API_KEY", "CEREBRAS_API_KEY", "MOONSHOT_API_KEY", "GROQ_API_KEY"):
    os.environ.pop(_k, None)
