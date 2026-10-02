import json
import re
import unittest

from council_v2 import consistency
from council_v2 import sources as S
from tests.helpers import FACULTY, REPOS_ROOT

DOC = json.loads((FACULTY / "alumni" / "alumni.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((FACULTY / "alumni" / "alumni.schema.json").read_text(encoding="utf-8"))
BY = {a["slug"]: a for a in DOC["alumni"]}
COUNCIL = json.loads((FACULTY / "council" / "council.json").read_text(encoding="utf-8"))


class AlumniJson(unittest.TestCase):
    def test_fourteen_records_with_required_fields(self):
        self.assertEqual(len(DOC["alumni"]), 14)
        self.assertEqual([a["number"] for a in DOC["alumni"]], list(range(1, 15)))
        req = SCHEMA["$defs"]["alumnus"]["required"]
        flags = SCHEMA["$defs"]["alumnus"]["properties"]["flags"]["required"]
        for a in DOC["alumni"]:
            for k in req:
                self.assertIn(k, a, (a["slug"], k))
            self.assertEqual(sorted(a["flags"]), sorted(flags), a["slug"])
            self.assertEqual(len(a["council"]["seats"]), 4)

    def test_contradictions_recorded_not_resolved(self):
        for a in DOC["alumni"]:
            self.assertIsNone(a["thesis"]["canonical"])
            if a["placement"]["name_review"]:
                self.assertIsNone(a["placement"]["canonical"])
        self.assertIsNone(BY["marco-aurelius"]["faculty_advisor"]["canonical"])
        self.assertGreaterEqual(len(BY["marco-aurelius"]["thesis"]["variants"]), 3)
        self.assertEqual(BY["costanza-notari"]["faculty_advisor"]["canonical"], "Claude Opus 4.7")

    def test_key_flags(self):
        self.assertTrue(BY["sofia-lume"]["flags"]["veto_pending"])
        self.assertTrue(BY["lucia-solari"]["flags"]["revisions_required_not_done"])
        self.assertTrue(BY["noa-cifratti"]["flags"]["revisions_required_not_done"])
        self.assertTrue(BY["noa-cifratti"]["flags"]["pronoun_inconsistency"])
        self.assertTrue(BY["tariq-al-khwarizmi"]["flags"]["multiple_commit_addresses"])
        for slug in ("ezio-cardone", "adele-maurique"):
            self.assertTrue(BY[slug]["flags"]["registry_tally_overstated"], slug)
            self.assertTrue(BY[slug]["flags"]["registry_scores_not_in_json"], slug)
        for slug in S.Q2:
            self.assertTrue(BY[slug]["flags"]["intake_contains_steering"], slug)
        for a in DOC["alumni"]:
            self.assertTrue(a["flags"]["zero_artifacts"], a["slug"])
            self.assertFalse(a["repo"]["has_code"])

    def test_council_block(self):
        ezio = BY["ezio-cardone"]["council"]
        self.assertEqual(ezio["quorum"]["seats_with_file"], 3)
        self.assertEqual(ezio["rule_based_tally"], "3/3")
        cer = next(s for s in ezio["seats"] if s["seat"] == "cerebras_reasoning")
        self.assertEqual((cer["status"], cer["file"], cer["overall_recorded"]), ("no_file", None, None))
        cos = next(s for s in BY["costanza-notari"]["council"]["seats"] if s["seat"] == "anthropic_chair")
        self.assertEqual((cos["overall_recorded"], cos["overall_recomputed"]), (9.36, 9.33))
        self.assertEqual(BY["sofia-lume"]["council"]["rule_based_outcome"], "VETO")

    def test_no_personal_addresses(self):
        raw = (FACULTY / "alumni" / "alumni.json").read_text(encoding="utf-8")
        emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", raw))
        self.assertTrue(emails)
        for e in emails:
            self.assertTrue(e.endswith("@aetherneum.com") and not e.startswith("aetherneum@"), e)
        self.assertNotIn("gmail", raw.lower())

    def test_email_pattern(self):
        for a in DOC["alumni"]:
            self.assertRegex(a["email"], r"@aetherneum\.com$")


class CouncilJson(unittest.TestCase):
    def test_seats(self):
        seats = {s["seat_id"]: s for s in COUNCIL["seats"]}
        self.assertEqual(seats["anthropic"]["model_planned"], "claude-opus-5-5")
        self.assertEqual(seats["dean"]["model_planned"], "claude-fable-5-1")
        self.assertFalse(seats["dean"]["voting"])
        self.assertFalse(COUNCIL["quorum"]["dean_votes"])
        self.assertEqual(COUNCIL["quorum"]["voting_seats"], ["anthropic", "reasoning", "longctx", "velocity"])
        for sid in ("reasoning", "longctx", "velocity"):
            self.assertEqual(seats[sid]["model_planned"], "[TO CONFIRM]")
        self.assertTrue(any("real long context" in c for c in seats["longctx"]["constraints"]))
        self.assertEqual(seats["longctx"]["model_recorded_2026Q2"], "moonshot-v1-32k")
        self.assertEqual(COUNCIL["quorum"]["min_valid_seats"], 3)


def surfaces(**over):
    base = {
        "alumnus_readme": {"name": "Ada Test", "role": "Engineer", "specialty": "Quiet Rigor", "advisor": "Claude Opus 4.7",
                           "placement": "Somewhere", "thesis": "One thesis"},
        "site_profile": {"name": "Ada Test", "role": "Engineer", "specialty": "Quiet Rigor", "advisor": "Claude Opus 4.7",
                         "placement": "Somewhere", "thesis": "One thesis"},
        "diploma_svg": {"name": "Ada Test", "specialty": "Quiet Rigor", "advisor": "Opus 4.7", "thesis": "One thesis"},
    }
    for k, v in over.items():
        surf, field = k.split("__")
        base[surf][field] = v
    return base


def alumnus(surf, **canon):
    a = {"slug": "ada-test", "flags": {}, "pronouns": {"canonical": "she/her"},
         "council": {"seats": [{"seat": s, "status": "file", "overall_recorded": 9.0, "overall_recomputed": 9.0,
                                "verdict_rule_based": "PASS"} for s in ("anthropic_chair", "cerebras_reasoning", "moonshot_longctx")]
                     + [{"seat": "groq_velocity", "status": "no_file"}]},
         "placement": {"name_review": False}}
    for field in consistency.FIELDS:
        pairs = S.values_for(field, surf, "ada-test")
        groups = S.group_values(pairs, S.keyfn_for(field))
        if field == "thesis":
            a["thesis"] = {"canonical": canon.get("thesis"), "variants": [{"text": g["value"], "where": g["where"]} for g in groups]}
        elif field == "specialty":
            a["specialty"] = {"poetic_name": canon.get("specialty"), "declared_values_found": groups}
        else:
            a.setdefault(field, {}).update({"canonical": canon.get(field), "declared_values_found": groups})
    return a


class Consistency(unittest.TestCase):
    def test_clean(self):
        s = surfaces()
        a = alumnus(s, faculty_advisor="Claude Opus 4.7", thesis="One thesis", name="Ada Test")
        self.assertEqual(consistency.check_alumnus(a, s), [])

    def test_mismatch_against_canonical(self):
        s = surfaces(diploma_svg__advisor="Sonnet 4.5")
        a = alumnus(s, faculty_advisor="Claude Opus 4.7")
        kinds = [(d.kind, d.field) for d in consistency.check_alumnus(a, s)]
        self.assertIn(("MISMATCH", "faculty_advisor"), kinds)

    def test_unresolved_without_canonical(self):
        s = surfaces(diploma_svg__thesis="Another thesis entirely")
        a = alumnus(s)
        divs = consistency.check_alumnus(a, s)
        self.assertIn(("UNRESOLVED", "thesis"), [(d.kind, d.field) for d in divs])

    def test_stale(self):
        s = surfaces()
        a = alumnus(s)
        s["site_profile"]["thesis"] = "Edited later"
        self.assertIn("STALE", [d.kind for d in consistency.check_alumnus(a, s)])

    def test_registry_overstated(self):
        s = surfaces()
        s["site_registry"] = {"claimed_tally": "4/4", "claimed_scores": ["9.3", "—", "9.1", "8.9"], "council": "4/4 PASS"}
        a = alumnus(s)
        regs = [d for d in consistency.check_alumnus(a, s) if d.kind == "REGISTRY"]
        self.assertTrue(any(d.field == "council tally" and d.found == "4/4" for d in regs))
        self.assertTrue(any(d.field.startswith("score") for d in regs))

    @unittest.skipUnless((REPOS_ROOT / "aetherneum-sites" / ".git").exists(), "sibling clones not present")
    def test_real_surfaces_at_main_diverge_and_exit_1(self):
        divs = consistency.check_all(DOC, repos_root=REPOS_ROOT, faculty_root=FACULTY, ref="main")
        kinds = consistency.summary(divs)
        self.assertGreater(len(divs), 0)
        self.assertNotIn("STALE", kinds)  # alumni.json was generated from main
        self.assertIn("REGISTRY", kinds)
        ezio = [d for d in divs if d.slug == "ezio-cardone" and d.kind == "REGISTRY"]
        self.assertTrue(any(d.found == "4/4" for d in ezio))


if __name__ == "__main__":
    unittest.main()
