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


class UiTest(unittest.TestCase):
    """w718: the w644 hub (#1251) passed every visual rule and a tour of stills; on Ben's Deck nearly every tab was
    broken (navy, Crafting cut to one row, no tech grid, the Blueprints preview off screen and flickering)."""

    FILES_1251 = ["Assets/Scripts/UI/Structured/StructuredHub.cs", "Assets/Scripts/UI/UiController.cs",
                  "Assets/Scripts/Steam/SteamInputBridge.cs", "Assets/Tests/UI/Structured/StructuredHubTests.cs"]
    UI_LINES = """Content: late-game audit save w718-lategame.zip (212 techs, 140 recipes, 24 blueprints, 9 fleets)
Full content: every tab's grid, list and tree whole or scrolling; fill 78-96 % per pane (ui_check fill)
Style: BlueprintPanelChild (touched) vs InvAndCraft/InventoryPanel: delta E 2.1 (on screen), alpha 1.00 vs 1.00, same art
Shots: proofs/shots.md, one line per still against Ben's words
Overlaps: 4 block pairs before, 4 after, 0 new (ui_layout.py, whole screen, block depth 2)
Alignment: max drift 0 px over the clusters (bottom-right HUD, top-left HUD); tolerance 2 px
"""

    def body(self):
        return (HERE / "fixtures" / "pr-1251-deck-hub.md").read_text(encoding="utf-8")

    def test_1251_passes_without_its_files_and_fails_the_ui_rules_with_them(self):
        self.assertEqual(pe.check(self.body())[0], [])
        reasons = "\n".join(pe.check(self.body(), self.FILES_1251)[0])
        for name in ("Content", "Full content", "Style", "Shots"):
            self.assertIn(f"UI change with no '{name}:' line", reasons)
        self.assertIn("'Clips' is a slideshow ('1 fps')", reasons)
        self.assertIn("no flicker result", reasons)

    def test_a_ui_section_with_full_content_style_shots_and_a_real_clip_passes(self):
        body = edit(GOOD, "Kind: visual, simulation", "Kind: ui, simulation")
        body = edit(body, "Clips: proofs/before.mp4, proofs/after.mp4 (the hand-over is at frames 118-190)",
                    self.UI_LINES + "Clips: proofs/before.mp4, proofs/after.mp4, 60 fps (each tab idle at 0-4 s, "
                    "hover at 4-8 s); ui_check flicker: 0 regions")
        self.assertEqual(self.problems(body), [])
        self.assertEqual(self.problems(body, ["Assets/Scripts/UI/Structured/StructuredHub.cs"]), [])

    def test_kind_ui_alone_brings_the_visual_rules(self):
        body = edit(GOOD, "Kind: visual, simulation", "Kind: ui, simulation")
        body = edit(body, "Built player: yes\n", "")
        self.assertIn("'Built player: yes' is missing", "\n".join(self.problems(body)))

    def test_a_ui_file_without_a_visual_kind_is_caught(self):
        body = edit(GOOD, "Kind: visual, simulation", "Kind: simulation")
        self.assertIn("say Kind: visual (ui for a screen)",
                      "\n".join(self.problems(body, ["Assets/Scripts/UI/Structured/StructuredHub.cs"])))

    def test_a_slideshow_is_named(self):
        for text in ("1 fps sequences of the tours' shots", "a sequence of the stills", "slideshow of screenshots"):
            self.assertTrue(pe.SLIDESHOW.search(text), text)
        for text in ("60 fps", "30 fps, 12 s", "frames 118-190"):
            self.assertFalse(pe.SLIDESHOW.search(text), text)

    def problems(self, body, files=None):
        return pe.check(body, files)[0]


class LayoutTest(unittest.TestCase):
    """w733: a UI change proves it left the rest of the screen as it was. #1272 (the Blueprints window on the Deck)
    turned the window opaque navy and passed an evidence check older than the rules that would have failed it; the
    same night the minimap's side buttons drifted off it and a slide-out covered the hotbar."""

    FILES_1272 = ["Assets/Scenes/main.unity", "Assets/Scripts/UI/Blueprints/BlueprintPanelFit.cs",
                  "Assets/UI/Components/BlueprintButton.prefab"]

    def body_1272(self):
        return (HERE / "fixtures" / "pr-1272-blueprints-navy.md").read_text(encoding="utf-8")

    def ui_body(self, **lines):
        body = edit(GOOD, "Kind: visual, simulation", "Kind: ui, simulation")
        body = edit(body, "Clips: proofs/before.mp4, proofs/after.mp4 (the hand-over is at frames 118-190)",
                    UiTest.UI_LINES + "Clips: proofs/before.mp4, proofs/after.mp4, 60 fps (each tab idle at 0-4 s); "
                    "ui_check flicker: 0 regions")
        for name, value in lines.items():
            body = re.sub(rf"^{name}:.*$", f"{name}: {value}", body, flags=re.MULTILINE)
        return body

    def reasons(self, body, files=None):
        return "\n".join(pe.check(body, files)[0])

    def test_1272_as_written_fails_on_the_layout_and_style_lines(self):
        reasons = self.reasons(self.body_1272(), self.FILES_1272)
        self.assertIn("no 'Overlaps:' line", reasons)
        self.assertIn("no 'Alignment:' line", reasons)
        self.assertIn("no 'Style:' line", reasons)

    def test_a_style_sentence_is_not_a_measurement(self):
        body = self.ui_body(Style="frame art unchanged, the panel keeps its translucent look at 1920x1080")
        self.assertIn("'Style:' has no measured delta E and alpha", self.reasons(body))

    def test_1272s_navy_fails_on_delta_e(self):
        line = ("GamePanels/BlueprintPanelChild/SolidBackdrop (new) vs GamePanels/InvAndCraft/InventoryPanel: delta E "
                "21.6 (on screen), alpha 0.98 vs 1.00, art 'flat fill' vs 'background-main'")
        self.assertIn("delta E 21.6 from the classic panel", self.reasons(self.ui_body(Style=line)))
        asked = line + '; intended (Ben): "make the blueprint panel solid dark navy"'
        self.assertNotIn("delta E 21.6 from the classic panel", self.reasons(self.ui_body(Style=asked)))

    def test_a_new_overlap_or_a_drift_fails(self):
        overlap = "4 block pairs before, 5 after, 1 new (ui_layout.py, whole screen, block depth 2)"
        self.assertIn("1 new overlap(s) between HUD blocks", self.reasons(self.ui_body(Overlaps=overlap)))
        drift = "max drift 14 px over the clusters (bottom-right HUD); tolerance 2 px"
        self.assertIn("'Alignment:' drifts 14 px", self.reasons(self.ui_body(Alignment=drift)))
        self.assertEqual(self.reasons(self.ui_body(Alignment="max drift 2 px over the clusters (bottom-right HUD)")), "")

    def test_the_scene_counts_as_ui(self):
        self.assertTrue(pe.UI_PATH.search("Assets/Scenes/main.unity"))
        self.assertIn("no 'Overlaps:' line", self.reasons(GOOD, ["Assets/Scenes/main.unity"]))

    def test_an_old_copy_says_so_and_the_verdict_names_its_version(self):
        self.assertIn("ff-agents 1.20.44, but 1.21.0 is released", pe.stale_problem("1.20.44", "1.21.0"))
        self.assertIsNone(pe.stale_problem("1.22.0", "1.22.0"))
        self.assertIsNone(pe.stale_problem("1.22.0", None))
        self.assertIn("ff-agents 9.9.9", pe.verdict_text([], [], "9.9.9"))


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
        files = [{"path": "Assets/Scripts/FFSystems/Presentation/RiderSystem.cs"}]
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
