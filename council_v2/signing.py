"""Ed25519 signing of Council records, behind a small interface.

Backends
--------
1. ``cryptography`` (preferred).  Used automatically when the package is
   importable.
2. ``pure-python-rfc8032`` (fallback).  A direct transcription of the
   reference implementation in RFC 8032 §6.  It produces byte-identical,
   standard Ed25519 signatures (Ed25519 is deterministic), so records signed
   with either backend verify with the other and with any standard tool.
   LIMITS: it is slow and NOT constant-time.  It is acceptable for signing
   public audit records on a trusted workstation; it is not a hardened
   implementation.  Install ``cryptography`` before the production re-defense
   (see README.md, "Signing keys").

There is deliberately no HMAC mode: an HMAC "signature" would need the same
secret to verify, which defeats a public ledger.

Record signatures
-----------------
``sign_record`` signs the canonical JSON of the record *without* its
``signature`` field (sorted keys, compact separators, UTF-8, no ASCII
escaping) and stores the signature block inside the record.  ``verify_record``
checks it against a public key supplied by the caller — never against the key
embedded in the record, which is informational only.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Pure-Python Ed25519 (RFC 8032 §6 reference implementation)
# --------------------------------------------------------------------------

_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493


def _modp_inv(x: int) -> int:
    return pow(x, _P - 2, _P)


_D = -121665 * _modp_inv(121666) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _sha512(b: bytes) -> bytes:
    return hashlib.sha512(b).digest()


def _sha512_modq(b: bytes) -> int:
    return int.from_bytes(_sha512(b), "little") % _Q


def _point_add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _P
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _P
    C = 2 * P[3] * Q[3] * _D % _P
    D = 2 * P[2] * Q[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _point_mul(s: int, P):
    Q = (0, 1, 1, 0)  # neutral element
    while s > 0:
        if s & 1:
            Q = _point_add(Q, P)
        P = _point_add(P, P)
        s >>= 1
    return Q


def _point_equal(P, Q) -> bool:
    if (P[0] * Q[2] - Q[0] * P[2]) % _P != 0:
        return False
    if (P[1] * Q[2] - Q[1] * P[2]) % _P != 0:
        return False
    return True


def _recover_x(y: int, sign: int):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _modp_inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_G_Y = 4 * _modp_inv(5) % _P
_G_X = _recover_x(_G_Y, 0)
_G = (_G_X, _G_Y, 1, _G_X * _G_Y % _P)


def _point_compress(P) -> bytes:
    zinv = _modp_inv(P[2])
    x = P[0] * zinv % _P
    y = P[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _point_decompress(s: bytes):
    if len(s) != 32:
        raise ValueError("invalid point length")
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _secret_expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError("Ed25519 secret seed must be 32 bytes")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def _pp_public_from_seed(seed: bytes) -> bytes:
    a, _ = _secret_expand(seed)
    return _point_compress(_point_mul(a, _G))


def _pp_sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _secret_expand(seed)
    A = _point_compress(_point_mul(a, _G))
    r = _sha512_modq(prefix + msg)
    Rs = _point_compress(_point_mul(r, _G))
    h = _sha512_modq(Rs + A + msg)
    s = (r + h * a) % _Q
    return Rs + int.to_bytes(s, 32, "little")


def _pp_verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _point_decompress(public)
    if not A:
        return False
    Rs = signature[:32]
    R = _point_decompress(Rs)
    if not R:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _Q:
        return False
    h = _sha512_modq(Rs + public + msg)
    sB = _point_mul(s, _G)
    hA = _point_mul(h, A)
    return _point_equal(sB, _point_add(R, hA))


# --------------------------------------------------------------------------
# Backend selection
# --------------------------------------------------------------------------

try:  # pragma: no cover - depends on the environment
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # type: ignore
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization  # type: ignore

    _HAVE_CRYPTOGRAPHY = True
except Exception:  # pragma: no cover
    _HAVE_CRYPTOGRAPHY = False


def backend_name(force_pure_python: bool = False) -> str:
    if _HAVE_CRYPTOGRAPHY and not force_pure_python:
        return "cryptography"
    return "pure-python-rfc8032"


def public_key_from_seed(seed: bytes, force_pure_python: bool = False) -> bytes:
    if _HAVE_CRYPTOGRAPHY and not force_pure_python:  # pragma: no cover
        priv = Ed25519PrivateKey.from_private_bytes(seed)
        return priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    return _pp_public_from_seed(seed)


def sign_bytes(seed: bytes, msg: bytes, force_pure_python: bool = False) -> bytes:
    if _HAVE_CRYPTOGRAPHY and not force_pure_python:  # pragma: no cover
        return Ed25519PrivateKey.from_private_bytes(seed).sign(msg)
    return _pp_sign(seed, msg)


def verify_bytes(public: bytes, msg: bytes, signature: bytes, force_pure_python: bool = False) -> bool:
    if _HAVE_CRYPTOGRAPHY and not force_pure_python:  # pragma: no cover
        try:
            Ed25519PublicKey.from_public_bytes(public).verify(signature, msg)
            return True
        except Exception:
            return False
    return _pp_verify(public, msg, signature)


# --------------------------------------------------------------------------
# Signer interface
# --------------------------------------------------------------------------


def key_id_for(public: bytes) -> str:
    """Short, stable identifier: first 16 hex chars of SHA-256(public key)."""
    return hashlib.sha256(public).hexdigest()[:16]


@dataclass
class Ed25519Signer:
    """Holds a 32-byte Ed25519 seed.  Never serialised into records."""

    seed: bytes
    label: str = "unlabelled"

    def __post_init__(self) -> None:
        if len(self.seed) != 32:
            raise ValueError("Ed25519 seed must be 32 bytes")
        self._public = public_key_from_seed(self.seed)

    @property
    def public_key(self) -> bytes:
        return self._public

    @property
    def key_id(self) -> str:
        return key_id_for(self._public)

    def sign(self, msg: bytes) -> bytes:
        return sign_bytes(self.seed, msg)

    @classmethod
    def generate(cls, label: str = "ephemeral") -> "Ed25519Signer":
        return cls(os.urandom(32), label=label)


def write_keypair(signer: Ed25519Signer, private_path: Path, public_path: Path) -> None:
    """Write the seed (hex) and public key (hex).  Refuses to overwrite."""
    private_path = Path(private_path)
    public_path = Path(public_path)
    for p in (private_path, public_path):
        if p.exists():
            raise FileExistsError(f"refusing to overwrite existing key file {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(
        "# Ed25519 seed (hex). SECRET. Never commit, never copy into a record.\n"
        f"# label: {signer.label}\n{signer.seed.hex()}\n",
        encoding="utf-8",
    )
    try:
        os.chmod(private_path, 0o600)
    except OSError:  # pragma: no cover - Windows ACLs differ
        pass
    public_path.write_text(
        f"# Ed25519 public key (hex). label: {signer.label} key_id: {signer.key_id}\n"
        f"{signer.public_key.hex()}\n",
        encoding="utf-8",
    )


def _read_hex_file(path: Path) -> bytes:
    lines = [
        ln.strip()
        for ln in Path(path).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        raise ValueError(f"no key material in {path}")
    return bytes.fromhex(lines[0])


def load_signer(private_path: Path, label: str | None = None) -> Ed25519Signer:
    return Ed25519Signer(_read_hex_file(private_path), label=label or Path(private_path).stem)


def load_public_key(public_path: Path) -> bytes:
    key = _read_hex_file(public_path)
    if len(key) != 32:
        raise ValueError(f"{public_path}: Ed25519 public key must be 32 bytes")
    return key


def default_public_key_path() -> Path | None:
    """Public key path from ``AETHERNEUM_COUNCIL_PUBKEY`` (configurable)."""
    env = os.environ.get("AETHERNEUM_COUNCIL_PUBKEY")
    return Path(env) if env else None


# --------------------------------------------------------------------------
# Record signing
# --------------------------------------------------------------------------

SIGNATURE_FIELD = "signature"


def canonical_bytes(record: dict[str, Any]) -> bytes:
    body = {k: v for k, v in record.items() if k != SIGNATURE_FIELD}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_record(record: dict[str, Any], signer: Ed25519Signer) -> dict[str, Any]:
    if SIGNATURE_FIELD in record:
        raise ValueError("record already carries a signature")
    payload = canonical_bytes(record)
    sig = signer.sign(payload)
    signed = dict(record)
    signed[SIGNATURE_FIELD] = {
        "alg": "Ed25519",
        "backend": backend_name(),
        "key_id": signer.key_id,
        "key_label": signer.label,
        "public_key_hex": signer.public_key.hex(),
        "payload": "canonical JSON of the record without 'signature' (sort_keys, separators=(',',':'), UTF-8)",
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "value_hex": sig.hex(),
    }
    return signed


@dataclass
class VerifyResult:
    ok: bool
    reason: str

    def __bool__(self) -> bool:  # allows ``if verify_record(...)``
        return self.ok


def verify_record(record: dict[str, Any], public_key: bytes) -> VerifyResult:
    sig = record.get(SIGNATURE_FIELD)
    if not isinstance(sig, dict):
        return VerifyResult(False, "unsigned")
    if sig.get("alg") != "Ed25519":
        return VerifyResult(False, f"unsupported alg {sig.get('alg')!r}")
    if sig.get("key_id") != key_id_for(public_key):
        return VerifyResult(False, "signed by a different key than the configured public key")
    try:
        value = bytes.fromhex(sig.get("value_hex", ""))
    except ValueError:
        return VerifyResult(False, "malformed signature hex")
    payload = canonical_bytes(record)
    if hashlib.sha256(payload).hexdigest() != sig.get("payload_sha256"):
        return VerifyResult(False, "payload hash mismatch (record modified after signing)")
    if not verify_bytes(public_key, payload, value):
        return VerifyResult(False, "Ed25519 verification failed")
    return VerifyResult(True, "ok")


def _main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Council v2 signing keys (Ed25519)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    kg = sub.add_parser("keygen", help="generate a new keypair (refuses to overwrite)")
    kg.add_argument("--private", required=True, type=Path)
    kg.add_argument("--public", required=True, type=Path)
    kg.add_argument("--label", default="council-v2")
    vf = sub.add_parser("verify", help="verify one signed record")
    vf.add_argument("record", type=Path)
    vf.add_argument("--public-key", type=Path, default=default_public_key_path())
    args = ap.parse_args(argv)
    if args.cmd == "keygen":
        signer = Ed25519Signer.generate(label=args.label)
        write_keypair(signer, args.private, args.public)
        print(f"key_id={signer.key_id} backend={backend_name()} public={args.public}")
        return 0
    if args.public_key is None:
        print("no public key: pass --public-key or set AETHERNEUM_COUNCIL_PUBKEY")
        return 2
    rec = json.loads(Path(args.record).read_text(encoding="utf-8"))
    res = verify_record(rec, load_public_key(args.public_key))
    print(f"{args.record}: {res.reason}")
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
