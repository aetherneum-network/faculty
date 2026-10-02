import json
import re
import tempfile
import unittest
from pathlib import Path

from council_v2 import registry
from council_v2.bundle import build_bundle
from council_v2.legacy import legacy_records
from council_v2.record import build_seat_record, write_signed
from council_v2.seats import MockSeat
from council_v2.signing import Ed25519Signer
from tests.helpers import FACULTY, FIXTURES, vec

COUNCIL = registry.load_council(FACULTY / "council" / "council.json")
LMAP = registry.legacy_map(COUNCIL)


def write_legacy(td: Path, signer: Ed25519Signer, cohort: str) -> None:
    for r in legacy_records(FACULTY, cohort, v2_seat_map=LMAP):
        write_signed(r, td / cohort / f"{r['candidate']['slug']}__{r['seat']['legacy_seat_id']}.json", signer)


class RegistryFromSignedJson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.td = Path(cls.tmp.name)
        cls.signer = Ed25519Signer.generate()
        write_legacy(cls.td, cls.signer, "cohort-q2-2026")
        write_legacy(cls.td, cls.signer, "cohort-phase-0")
        cls.rows, cls.rejected = registry.build([cls.td], cls.signer.public_key, COUNCIL)
        cls.by = {r.slug: r for r in cls.rows}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ezio_is_3_of_3_not_4_of_4(self):
        d = self.by["ezio-cardone"].decision
        self.assertEqual(d.tally, "3/3")
        self.assertNotEqual(d.tally, "4/4")
        self.assertEqual(d.null_seats, ["reasoning"])  # the Cerebras seat wrote no file
        self.assertTrue(d.reduced_quorum)
        md = registry.to_markdown(self.rows, COUNCIL)
        line = next(ln for ln in md.splitlines() if "ezio-cardone" in ln.lower() or "Documentary Cadence" in ln)
        self.assertIn("3/3 PASS", line)
        self.assertNotIn("4/4", line)
        self.assertIn("null (no_file)", line)

    def test_registry_scores_exist_in_json(self):
        """The site Registry showed 9.3 / 9.1 / 8.9 for Ezio; none of these exists in a JSON."""
        md = registry.to_markdown(self.rows, COUNCIL)
        line = next(ln for ln in md.splitlines() if "Documentary Cadence" in ln)
        shown = set(re.findall(r"\b\d\.\d\d\b", line))
        allowed = set()
        for seat in ("anthropic_chair", "moonshot_longctx", "groq_velocity"):
            d = json.loads((FACULTY / "cohort-q2-2026" / "council-reviews" / f"ezio-cardone__{seat}.json").read_text(encoding="utf-8"))
            from council_v2.scoring import score_seat
            allowed.add(f"{score_seat(d['criterion_scores']).overall:.2f}")
        self.assertTrue(shown <= allowed, (shown, allowed))
        for invented in ("9.30", "9.10", "8.90"):
            self.assertNotIn(invented, shown)

    def test_adele_and_tomaso_reduced_quorum(self):
        for slug in ("adele-maurique", "tomaso-riviera"):
            d = self.by[slug].decision
            self.assertEqual(d.tally, "3/3")
            self.assertEqual(d.null_seats, ["anthropic"])

    def test_costanza_4_of_4(self):
        self.assertEqual(self.by["costanza-notari"].decision.tally, "4/4")

    def test_sofia_is_vetoed(self):
        self.assertEqual(self.by["sofia-lume"].decision.outcome, "VETO")

    def test_all_fourteen_and_nothing_rejected(self):
        self.assertEqual(len(self.rows), 14)
        self.assertEqual(self.rejected, [])

    def test_html_fragment_escapes_and_lists_rows(self):
        h = registry.to_html(self.rows, COUNCIL)
        self.assertEqual(h.count("<tr class="), 14)
        self.assertIn('data-slug="ezio-cardone"', h)


class RejectsUnverifiable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.td = Path(self.tmp.name)
        self.signer = Ed25519Signer.generate()
        write_legacy(self.td, self.signer, "cohort-q2-2026")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tampered_record_is_rejected(self):
        p = self.td / "cohort-q2-2026" / "ezio-cardone__anthropic_chair.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["scores_raw"]["body_of_work_depth"] = 10
        p.write_text(json.dumps(d), encoding="utf-8")
        rows, rejected = registry.build([self.td], self.signer.public_key, COUNCIL)
        self.assertTrue(any("ezio-cardone__anthropic_chair" in f and "modified" in why for f, why in rejected))
        ezio = next(r for r in rows if r.slug == "ezio-cardone")
        self.assertEqual(ezio.decision.tally, "2/2")  # the tampered seat cannot contribute
        self.assertEqual(ezio.decision.outcome, "NO_QUORUM")

    def test_unsigned_json_is_rejected(self):
        # a 2026-style JSON dropped into the ledger never reaches the Registry
        src = FACULTY / "cohort-q2-2026" / "council-reviews" / "costanza-notari__anthropic_chair.json"
        (self.td / "stray.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        _, rejected = registry.build([self.td], self.signer.public_key, COUNCIL)
        self.assertTrue(any(f.endswith("stray.json") for f, _ in rejected))

    def test_other_key_is_rejected(self):
        _, rejected = registry.build([self.td], Ed25519Signer.generate().public_key, COUNCIL)
        self.assertEqual(len(rejected), 16)

    def test_mock_records_excluded_by_default(self):
        bundle = build_bundle("tiny-repo", faculty_root=FACULTY, profile_path=FIXTURES / "tiny_repo" / "README.md")
        session = {"session_id": "mock-1", "started_at": "2099-01-01T00:00:00Z", "dry_run": True, "mock": True}
        for sid in ("anthropic", "reasoning", "longctx", "velocity"):
            res = MockSeat(sid, scores=vec(10, 10, 10, 10, 10, 10, 10)).score(bundle)
            rec = build_seat_record(session, {"role": sid, "voting": True}, res, bundle, candidate={"slug": "tiny-repo", "name": "Tiny"})
            write_signed(rec, self.td / "mock" / f"tiny-repo__{sid}.json", self.signer)
        rows, _ = registry.build([self.td], self.signer.public_key, COUNCIL)
        self.assertNotIn("tiny-repo", {r.slug for r in rows})
        rows, _ = registry.build([self.td], self.signer.public_key, COUNCIL, include_mock=True)
        self.assertIn("tiny-repo", {r.slug for r in rows})


if __name__ == "__main__":
    unittest.main()
