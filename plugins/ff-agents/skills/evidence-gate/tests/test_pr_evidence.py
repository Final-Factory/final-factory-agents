"""Offline tests for pr_evidence.py. No network, no gh.

    python3 -m unittest discover -s plugins/ff-agents/skills/evidence-gate/tests -p 'test_*.py' -v
"""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import pr_evidence as pe  # noqa: E402

GOOD = """**TL;DR:** riders are drawn on their seats.

## Evidence

Kind: visual, simulation   <!-- visual | simulation | other -->

| Claim | Basis | Where |
|---|---|---|
| A remote rider is drawn on their seat | MEASURED: stepped frames 118-190 of the built-player clip | proofs/after.mp4 |
| The hand-over op applies on the same heartbeat on both peers | MEASURED: two-peer audit, 2354 shared heartbeats | proofs/audit.txt |

Intended look (Ben): "the other player appears outside of the ship behind it" must not happen
Built player: yes
Clips: proofs/before.mp4, proofs/after.mp4 (the hand-over is at frames 118-190)
Looked: yes, every frame of 118-190 at 2x crop
Review: watch_video report in proofs/review/; no blind model review (no Gemini key here)

Tests: FFEditorTests 6494 run, 6479 passed, 0 failed
Determinism audit: 2354 shared heartbeats, no divergence
Save compatibility: none, no saved state is touched

Not verified: nothing

## Save compatibility

None.
"""


def edit(body, old, new):
    assert old in body, old
    return body.replace(old, new)


class CheckTest(unittest.TestCase):
    def problems(self, body, files=None):
        return pe.check(body, files)[0]

    def assertFails(self, body, *fragments, files=None):
        problems = "\n".join(self.problems(body, files))
        for fragment in fragments:
            self.assertIn(fragment, problems)

    def test_a_complete_section_passes(self):
        self.assertEqual(self.problems(GOOD), [])
        self.assertEqual(self.problems(GOOD, ["Assets/Scripts/FFSystems/Presentation/RiderSystem.cs",
                                              "Assets/Scripts/FFSystems/Construction/HandOverSystem.cs"]), [])
        self.assertIn("evidence-gate: PASS", pe.verdict_text([], []))

    def test_no_section_fails(self):
        self.assertFails("**TL;DR:** fixed.\n\n## Tests\n\nGreen.", "no '## Evidence' section")

    def test_the_section_ends_at_the_next_heading(self):
        section = pe.evidence_section(GOOD)
        self.assertIn("Not verified: nothing", section)
        self.assertNotIn("None.", section)
        self.assertNotIn("<!--", section)

    def test_a_guess_is_not_a_basis(self):
        body = edit(GOOD, "MEASURED: stepped frames 118-190 of the built-player clip", "GUESS")
        self.assertFails(body, "'A remote rider is drawn on their seat' rests on a guess")
        body = edit(GOOD, "MEASURED: stepped frames 118-190 of the built-player clip", "looks right to me")
        self.assertFails(body, "the basis starts with MEASURED or SOURCED")
        body = edit(GOOD, "MEASURED: stepped frames 118-190 of the built-player clip", "MEASURED")
        self.assertFails(body, "MEASURED needs what was measured or the source")

    def test_nothing_may_be_pending(self):
        body = edit(GOOD, "Review: watch_video report in proofs/review/; no blind model review (no Gemini key here)",
                    "Review: the watch_video review is pending on BEAST")
        self.assertFails(body, "something is still 'pending': no merge before the review is finished")
        # the honest place for what is open is the Not verified line
        body = edit(GOOD, "Not verified: nothing", "Not verified: the long-flight case, not yet reproduced")
        self.assertEqual(self.problems(body), [])
        self.assertFails(edit(GOOD, "Not verified: nothing\n", ""), "no 'Not verified:' line")

    def test_visual_needs_a_built_player_the_events_place_the_look_and_a_look(self):
        self.assertFails(edit(GOOD, "Built player: yes", "Built player: no, the sandbox editor is occluded"),
                         "'Built player: yes' is missing")
        self.assertFails(edit(GOOD, " (the hand-over is at frames 118-190)", ""),
                         "'Clips' does not say where the event is")
        self.assertFails(edit(GOOD, "Clips: proofs/before.mp4, proofs/after.mp4 (the hand-over is at frames 118-190)",
                              "Clips: proofs/2026-10-02/ (stills)"), "no 'Clips:' line naming a before and an after clip")
        self.assertFails(edit(GOOD, "Looked: yes, every frame of 118-190 at 2x crop", "Looked: watch_video says PASS"),
                         "'Looked: yes, ...' is missing")
        self.assertFails(edit(GOOD, "Intended look (Ben):", "Intended look:"), "does not say whose words they are")
        self.assertFails(edit(GOOD, 'Intended look (Ben): "the other player appears outside of the ship behind it" must not happen\n', ""),
                         "no 'Intended look (who): ...' line")
        for place in ("after.mp4 (the event is at 2.4 s)", "after.mp4, the pickup at 0:12", "after.mp4 frame 164"):
            body = edit(GOOD, "proofs/after.mp4 (the hand-over is at frames 118-190)", place)
            self.assertEqual(self.problems(body), [], place)

    def test_simulation_needs_tests_the_audit_and_save_compatibility(self):
        self.assertFails(edit(GOOD, "Determinism audit: 2354 shared heartbeats, no divergence\n", ""),
                         "no 'Determinism audit:' line")
        self.assertFails(edit(GOOD, "Determinism audit: 2354 shared heartbeats, no divergence", "Determinism audit: clean"),
                         "does not give the number of heartbeats compared")
        self.assertFails(edit(GOOD, "Tests: FFEditorTests 6494 run, 6479 passed, 0 failed\n", ""), "no 'Tests:' line")
        self.assertFails(edit(GOOD, "Save compatibility: none, no saved state is touched\n", ""),
                         "no 'Save compatibility:' line")
        skipped = edit(GOOD, "Determinism audit: 2354 shared heartbeats, no divergence",
                       "Determinism audit: not needed, the change only renames a private method")
        problems, notes = pe.check(skipped)
        self.assertEqual(problems, [])
        self.assertIn("determinism audit skipped", notes[0])
        self.assertFails(edit(GOOD, "Determinism audit: 2354 shared heartbeats, no divergence", "Determinism audit: not needed"),
                         "has to say why")

    def test_the_changed_files_have_to_match_the_kind(self):
        other = edit(GOOD, "Kind: visual, simulation", "Kind: other")
        self.assertFails(other, "the changed files look visual", files=["Assets/Scripts/UI/Crafting/QuickCraftPanel.cs"])
        self.assertFails(other, "the changed files look visual", files=["Assets/Shaders/Exhaust.shader"])
        self.assertFails(other, "simulation code changed", files=["Assets/Scripts/FFSystems/Construction/HandOverSystem.cs"])
        visual = edit(GOOD, "Kind: visual, simulation", "Kind: visual")
        # presentation systems live under FFSystems/Presentation: they are not simulation
        self.assertEqual(self.problems(visual, ["Assets/Scripts/FFSystems/Presentation/RiderSystem.cs",
                                                "Assets/Tests/Presentation/RiderTest.cs"]), [])
        self.assertFails(visual, "simulation code changed", files=["Assets/Scripts/FFCore/Time/Heartbeat.cs"])
        claimed = edit(visual, "| The hand-over op applies on the same heartbeat on both peers | MEASURED: two-peer audit, 2354 shared heartbeats |",
                       "| No simulation state changes | MEASURED: two-peer audit, 2354 shared heartbeats |")
        self.assertEqual(self.problems(claimed, ["Assets/Scripts/FFCore/Time/Heartbeat.cs"]), [])
        self.assertFails(edit(GOOD, "Kind: visual, simulation", "Kind: pretty"), "no 'Kind:' line")

    def test_docs_tools_and_tests_need_no_section(self):
        self.assertFalse(pe.applies(["docs/HowToPlay.md", "scripts/feel/run.py", "Assets/Tests/Combat/HullTest.cs",
                                     "Assets/Editor/Gallery.cs", "Assets/Scripts/UI/Panel.cs.meta"]))
        self.assertTrue(pe.applies(["docs/HowToPlay.md", "Assets/Scripts/UI/Crafting/QuickCraftPanel.cs"]))


class ReplayTest(unittest.TestCase):
    """Three pull requests of 2026-10-01/02, each with the Evidence section its own description supports."""

    def reasons(self, name, files):
        return "\n".join(pe.check((HERE / "fixtures" / name).read_text(encoding="utf-8"), files)[0])

    def test_913_quick_craft_fails_on_the_pending_review(self):
        reasons = self.reasons("pr-913-quick-craft.md", ["Assets/Scripts/UI/Crafting/QuickCraftNeeds.cs",
                                                         "Assets/Scripts/UI/Crafting/QuickCraftPanel.cs"])
        self.assertIn("something is still 'pending': no merge before the review is finished", reasons)
        self.assertIn("'Built player: yes' is missing", reasons)
        self.assertIn("'Clips' does not say where the event is", reasons)
        self.assertIn("'Looked: yes, ...' is missing", reasons)

    def test_886_miner_explosions_fails_on_the_built_player(self):
        reasons = self.reasons("pr-886-miner-explosions.md",
                               ["Assets/Scripts/FFSystems/Presentation/DeathExplosionVfxSystem.cs",
                                "Assets/Editor/DeathExplosionVfxGallery.cs", "Assets/Tests/Combat/DeathExplosionHullTest.cs"])
        self.assertIn("'Built player: yes' is missing", reasons)
        self.assertIn("no 'Intended look (who): ...' line", reasons)
        self.assertIn("'Looked: yes, ...' is missing", reasons)
        self.assertNotIn("simulation code changed", reasons)

    def test_884_station_riders_fails_on_the_look(self):
        reasons = self.reasons("pr-884-station-riders.md",
                               ["Assets/Scripts/FFSystems/Presentation/StationRiderPresentationSystem.cs",
                                "Assets/Scripts/FFComponents/Presentation/StationPoseTrack.cs",
                                "Assets/Scripts/UI/World/PlayerNameTagController.cs"])
        self.assertIn("'Looked: yes, ...' is missing", reasons)
        self.assertIn("'Clips' does not say where the event is", reasons)
        self.assertNotIn("Built player", reasons)       # it had built players and Ben's words; nobody had looked
        self.assertNotIn("Intended look", reasons)


class UsedByTest(unittest.TestCase):
    """w438: a shader or material change lists everything that uses it. #1068 changed the sprite shader 25
    materials share and checked only the Alt-view icons; every range ring in 0.50.0.77 filled dark."""

    FILES_1068 = ["Assets/Art/Shaders/AltIconBacking.hlsl", "Assets/Art/Shaders/AltIconBacking.hlsl.meta",
                  "Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph",
                  "Assets/Resources/ItemEntities/NetworkedStorageHoldEntity.prefab",
                  "Assets/Scripts/ControllerSystems/ActiveItemIconScaleSystem.cs",
                  "Assets/Scripts/FFSystems/Indicators/ActiveItemDisplaySystem.cs", "Assets/Tests/UI/CargoHoldAltViewIconTest.cs"]
    FILES_1076 = ["Assets/Art/Materials/AsteroWorldSpriteMat.mat", "Assets/Art/Shaders/AltIconBacking.hlsl",
                  "Assets/Art/Shaders/AltIconSprite.ShaderGraph", "Assets/Art/Shaders/AltIconSprite.ShaderGraph.meta",
                  "Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph", "Assets/Scripts/ControllerSystems/AltIconBacking.cs",
                  "Assets/Tests/Presentation/AltIconBackingScopeTest.cs"]

    def body(self, name):
        return (HERE / "fixtures" / name).read_text(encoding="utf-8")

    def test_1068_as_written_fails_only_on_the_missing_used_by(self):
        problems = pe.check(self.body("pr-1068-alt-icon-backing.md"), self.FILES_1068)[0]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("AsteroWorldSprite.ShaderGraph with no '## Used by' section", problems[0])
        self.assertEqual(pe.check(self.body("pr-1068-alt-icon-backing.md"), [f for f in self.FILES_1068
                                                                             if "Art/Shaders" not in f])[0], [])

    def test_1076_with_its_users_listed_passes(self):
        self.assertEqual(pe.check(self.body("pr-1076-shaped-hover-darkness.md"), self.FILES_1076)[0], [])

    def test_a_dropped_row_or_a_weak_basis_fails(self):
        body = self.body("pr-1076-shaped-hover-darkness.md")
        dropped = re.sub(r"^\| `Assets/Resources/Icons/IconMaterial/NoFuelMat.mat` \|.*\n", "", body, flags=re.MULTILINE)
        self.assertIn("the tool found 24 users and the table has 23 rows", "\n".join(pe.check(dropped, self.FILES_1076)[0]))
        guessed = re.sub(r"(\| `Assets/Art/Materials/InserterArrow.mat` \| )[^|]*\|", r"\1GUESS: arrows are opaque |", body)
        self.assertIn("InserterArrow.mat: the basis starts with TARGET, MEASURED or SOURCED (a guess is not a basis)",
                      "\n".join(pe.check(guessed, self.FILES_1076)[0]))
        unmeasured = re.sub(r"(\| `Assets/Art/Materials/InserterArrow.mat` \| )[^|]*\|",
                            r"\1MEASURED: looked at it in the editor scene |", body)
        self.assertIn("MEASURED needs a built-player before/after",
                      "\n".join(pe.check(unmeasured, self.FILES_1076)[0]))

    def test_a_material_counts_as_visual(self):
        self.assertTrue(pe.VISUAL_PATH.search("Assets/Art/Materials/Glow.mat"))
        self.assertTrue(pe.VISUAL_PATH.search("Assets/Art/Shaders/AsteroWorldSprite.ShaderGraph"))


class AuditTest(unittest.TestCase):
    def test_a_pass_counts_only_when_it_was_posted_before_the_merge(self):
        files = [{"path": "Assets/Scripts/UI/Crafting/QuickCraftPanel.cs"}]
        prs = [
            {"number": 1, "title": "checked, then merged", "mergedAt": "2026-10-02T06:10:53Z", "body": GOOD, "files": files,
             "comments": [{"body": "evidence-gate: PASS (pr_evidence.py)", "createdAt": "2026-10-02T06:01:00Z"}]},
            {"number": 2, "title": "merged, then checked", "mergedAt": "2026-10-02T06:10:53Z", "body": GOOD, "files": files,
             "comments": [{"body": "evidence-gate: PASS (pr_evidence.py)", "createdAt": "2026-10-02T07:00:00Z"}]},
            {"number": 3, "title": "no section", "mergedAt": "2026-10-02T06:10:53Z", "body": "fixed", "files": files, "comments": []},
            {"number": 4, "title": "docs only", "mergedAt": "2026-10-02T06:10:53Z", "body": "", "files": [{"path": "docs/a.md"}],
             "comments": []},
        ]
        rows = {r["number"]: r for r in pe.audit_rows(prs)}
        self.assertEqual((rows[1]["verdict"], rows[1]["before_merge"]), ("PASS", "yes"))
        self.assertEqual((rows[2]["verdict"], rows[2]["before_merge"]), ("PASS", "no"))
        self.assertEqual((rows[3]["verdict"], rows[3]["before_merge"]), ("FAIL", "no"))
        self.assertIn("no '## Evidence' section", rows[3]["why"])
        self.assertEqual(rows[4]["verdict"], "n/a")


if __name__ == "__main__":
    unittest.main()
