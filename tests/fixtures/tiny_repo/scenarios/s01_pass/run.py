"""Passes only if the executor stripped secret-looking environment variables."""
import os
import sys

leaked = [k for k in os.environ if any(w in k.upper() for w in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))]
print("leaked:", leaked)
sys.exit(1 if leaked else 0)
