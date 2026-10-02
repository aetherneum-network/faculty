import json
import tempfile
import unittest
from pathlib import Path

from council_v2 import signing
from council_v2.signing import Ed25519Signer, load_public_key, load_signer, sign_record, verify_record, write_keypair


class RFC8032Vectors(unittest.TestCase):
    """RFC 8032 §7.1, TEST 1 and TEST 2."""

    def test_vector_1(self):
        sk = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        pk = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        sig = bytes.fromhex("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065"
                            "224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertEqual(signing.public_key_from_seed(sk, force_pure_python=True), pk)
        self.assertEqual(signing.sign_bytes(sk, b"", force_pure_python=True), sig)
        self.assertTrue(signing.verify_bytes(pk, b"", sig, force_pure_python=True))
        self.assertFalse(signing.verify_bytes(pk, b"x", sig, force_pure_python=True))

    def test_vector_2(self):
        sk = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
        pk = bytes.fromhex("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
        sig = bytes.fromhex("92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
                            "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")
        self.assertEqual(signing.public_key_from_seed(sk, force_pure_python=True), pk)
        self.assertEqual(signing.sign_bytes(sk, bytes([0x72]), force_pure_python=True), sig)


class RecordRoundTrip(unittest.TestCase):
    def setUp(self):
        self.signer = Ed25519Signer.generate("test")
        self.rec = {"schema": "x", "candidate": {"slug": "ezio-cardone", "name": "Ezio Cardone"},
                    "scores_raw": {"body_of_work_depth": 9}, "note": "Æther · è à ü"}

    def test_round_trip(self):
        signed = sign_record(self.rec, self.signer)
        self.assertTrue(verify_record(signed, self.signer.public_key).ok)
        again = json.loads(json.dumps(signed, indent=2, ensure_ascii=False))  # pretty-printing does not matter
        self.assertTrue(verify_record(again, self.signer.public_key).ok)

    def test_tamper_detected(self):
        signed = sign_record(self.rec, self.signer)
        signed["scores_raw"]["body_of_work_depth"] = 10
        self.assertFalse(verify_record(signed, self.signer.public_key).ok)

    def test_signature_value_tamper_detected(self):
        signed = sign_record(self.rec, self.signer)
        v = signed["signature"]["value_hex"]
        signed["signature"]["value_hex"] = ("0" if v[0] != "0" else "1") + v[1:]
        self.assertFalse(verify_record(signed, self.signer.public_key).ok)

    def test_embedded_key_is_not_trusted(self):
        mallory = Ed25519Signer.generate("mallory")
        forged = sign_record(self.rec, mallory)  # embeds mallory's public key
        self.assertFalse(verify_record(forged, self.signer.public_key).ok)

    def test_unsigned(self):
        self.assertEqual(verify_record(self.rec, self.signer.public_key).reason, "unsigned")

    def test_keypair_files(self):
        with tempfile.TemporaryDirectory() as td:
            priv, pub = Path(td) / "k.key", Path(td) / "k.pub"
            write_keypair(self.signer, priv, pub)
            self.assertEqual(load_public_key(pub), self.signer.public_key)
            self.assertEqual(load_signer(priv).key_id, self.signer.key_id)
            with self.assertRaises(FileExistsError):
                write_keypair(self.signer, priv, pub)
            self.assertNotIn(self.signer.seed.hex(), pub.read_text())


if __name__ == "__main__":
    unittest.main()
