"""Rehearsal chain (prova generale, 2026-09-30): three small changes, one test each.

1. ``--marker``: a dry-run session can carry a visible label; it lives in the
   session block, so it is inside the signed payload of every record.
2. Registry: a mock / dry-run row (only reachable with ``include_mock=True``)
   says so in its own cells and in a banner; it never reads "Council v2
   session, signed at run".
3. ``default_inputs``: with ``--repo`` the README fallback of the profile is
   read from that repository, not from ``<repos_root>/<slug>``.

Offline, mock seats, ephemeral keys.
"""

import json
import tempfile
import unittest
from pathlib import Path

from council_v2 import registry
from council_v2 import run_council_v2 as rc
from council_v2.legacy import legacy_records
from council_v2.record import load_records, write_signed
from council_v2.signing import Ed25519Signer, verify_record
from tests.helpers import FACULTY, FIXTURES

COUNCIL = registry.load_council(FACULTY / "council" / "council.json")
MARKER = "REHEARSAL — mock seats, test key — not a Council verdict"


class _Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.signer = Ed25519Signer.generate("test")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kw):
        args = dict(repos_root=FACULTY.parent, out_root=self.out / "records", signer=self.signer, dry_run=True, mock=True,
                    intake=None, profile=FIXTURES / "tiny_repo" / "README.md", repo=FIXTURES / "tiny_repo",
                    seats=rc.build_mock_seats(COUNCIL))
        args.update(kw)
        return rc.run("tiny-repo", **args)


class SessionMarker(_Run):
    def test_marker_is_in_the_signed_payload_of_every_record(self):
        s = self._run(marker=MARKER)
        files = sorted(Path(s["out"]).rglob("*.json"))
        self.assertEqual(len(files), 6 + 1 + 8)  # candidate records + calibration summary + 2 decoys x 4 seats
        for f in files:
            rec = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(rec["session"]["marker"], MARKER, f.name)
            self.assertTrue(verify_record(rec, self.signer.public_key).ok, f.name)
        # removing the marker after signing is detected
        rec = json.loads(files[0].read_text(encoding="utf-8"))
        del rec["session"]["marker"]
        res = verify_record(rec, self.signer.public_key)
        self.assertFalse(res.ok)
        self.assertIn("modified after signing", res.reason)

    def test_no_marker_key_unless_asked(self):
        s = self._run()
        rec = json.loads((Path(s["out"]) / "tiny-repo__anthropic.json").read_text(encoding="utf-8"))
        self.assertNotIn("marker", rec["session"])

    def test_marker_is_recorded_on_a_lint_block_too(self):
        from council_v2.bundle import SteeringError

        with self.assertRaises(SteeringError):
            self._run(marker=MARKER, intake=FACULTY / "cohort-q2-2026" / "intake" / "costanza-notari.md")
        blocked = list(self.out.rglob("*__LINT_BLOCKED.json"))
        self.assertEqual(len(blocked), 1)
        self.assertEqual(json.loads(blocked[0].read_text(encoding="utf-8"))["session"]["marker"], MARKER)

    def test_marker_is_refused_in_a_live_run(self):
        with self.assertRaises(rc.RunRefused):
            self._run(marker=MARKER, dry_run=False, mock=False)
        self.assertEqual(list(self.out.rglob("*.json")), [])  # refused before anything is written
        self.assertEqual(rc.main(["--slug", "tiny-repo", "--live", "--marker", MARKER]), 2)


class RegistryLabelsMockRows(_Run):
    def test_mock_row_is_labelled_in_cells_banner_and_class(self):
        s = self._run(marker=MARKER)
        rows, rejected = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True)
        self.assertEqual(rejected, [])
        self.assertEqual([r.slug for r in rows], ["tiny-repo"])
        row = rows[0]
        self.assertTrue(row.mock)
        self.assertEqual(row.marker, MARKER)
        self.assertTrue(row.provenance.startswith(registry.MOCK_PROVENANCE))
        self.assertIn(MARKER, row.provenance)
        md = registry.to_markdown(rows, COUNCIL)
        line = next(ln for ln in md.splitlines() if ln.startswith("| ") and "tiny-repo" in ln)
        self.assertIn(MARKER, line)
        self.assertNotIn("Council v2 session, signed at run", md)
        self.assertTrue(any(ln.startswith("> **") and MARKER in ln for ln in md.splitlines()))
        h = registry.to_html(rows, COUNCIL)
        self.assertIn('<p class="registry-mock-banner">', h)
        self.assertIn('class="outcome-pass registry-mock" data-slug="tiny-repo"', h)
        self.assertEqual(h.count(MARKER), 2)  # banner + the row's provenance cell
        self.assertEqual(h.count("<tr class="), 1)

    def test_mock_row_without_marker_still_says_mock(self):
        s = self._run()
        rows, _ = registry.build([s["out"]], self.signer.public_key, COUNCIL, include_mock=True)
        self.assertEqual(rows[0].provenance, registry.MOCK_PROVENANCE)
        self.assertIn(registry.MOCK_PROVENANCE, registry.to_html(rows, COUNCIL))

    def test_mock_rows_stay_out_by_default(self):
        s = self._run(marker=MARKER)
        rows, rejected = registry.build([s["out"]], self.signer.public_key, COUNCIL)
        self.assertEqual((rows, rejected), ([], []))

    def test_real_rows_carry_no_banner(self):
        td = self.out / "legacy"
        lmap = registry.legacy_map(COUNCIL)
        for r in legacy_records(FACULTY, "cohort-q2-2026", v2_seat_map=lmap):
            write_signed(r, td / f"{r['candidate']['slug']}__{r['seat']['legacy_seat_id']}.json", self.signer)
        rows, _ = registry.build([td], self.signer.public_key, COUNCIL)
        self.assertTrue(rows)
        self.assertFalse(any(r.mock for r in rows))
        self.assertIsNone(registry.mock_banner(rows))
        self.assertNotIn("registry-mock", registry.to_html(rows, COUNCIL))
        self.assertNotIn("> **", registry.to_markdown(rows, COUNCIL))
        recs, _ = load_records([td], self.signer.public_key)
        self.assertTrue(all("marker" not in r["session"] for r in recs))


class DefaultProfileFollowsRepo(unittest.TestCase):
    def test_readme_fallback_comes_from_the_given_repo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            frozen = FIXTURES / "tiny_repo"
            got = rc.default_inputs("no-pending-profile-for-this-slug", root, frozen)
            self.assertEqual(got["profile"], frozen / "README.md")
            self.assertEqual(got["repo"], frozen)
            self.assertIsNone(got["intake"])

    def test_without_repo_the_old_default_is_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            got = rc.default_inputs("no-pending-profile-for-this-slug", root)
            self.assertEqual(got["profile"], root / "no-pending-profile-for-this-slug" / "README.md")
            self.assertEqual(got["repo"], root / "no-pending-profile-for-this-slug")

    def test_pending_profile_still_wins(self):
        got = rc.default_inputs("costanza-notari", FACULTY.parent, FIXTURES / "tiny_repo")
        self.assertEqual(got["profile"], FACULTY / "alumni" / "pending" / "costanza-notari.md")
        self.assertEqual(got["repo"], FIXTURES / "tiny_repo")


if __name__ == "__main__":
    unittest.main()
