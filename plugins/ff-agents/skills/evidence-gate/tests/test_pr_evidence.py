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


def without_closeups(problems):
    """The w1567 close-up rule, left out where a test is about another rule (CloseUpTest covers it)."""
    return [p for p in problems if "Close-ups" not in p]

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

    def test_a_measurement_table_in_the_section_is_named(self):
        # w1648: a before/after table inside ## Evidence was read as claims, one "basis" problem per row
        table = "| leg | fps | CPU ms a second |\n|---|---|---|\n| before | 62 | 2530 |\n| after | 66 | 2357 |\n"
        body = edit(GOOD, "Not verified: nothing", table + "\nNot verified: nothing")
        self.assertFails(body, "a measurement table is not the claims table")
        body = edit(GOOD, "## Save compatibility", "## Measured\n\n" + table + "\n## Save compatibility")
        self.assertEqual(self.problems(body), [])

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

    def test_an_objective_card_change_needs_a_built_player(self):
        # w918: PR #1408 changed a tutorial tip's icons as 'Kind: other' with editor stills only
        other = edit(GOOD, "Kind: visual, simulation", "Kind: other")
        card = ["Assets/Resources/Objectives/ObjectivesTryHard/3z_CraftMiningStationTH.asset"]
        self.assertFails(other.replace("Built player: yes", "Built player: no"), "tutorial or objective cards changed", files=card)
        self.assertNotIn("tutorial or objective cards changed", " ".join(self.problems(other, card)))

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
Overlaps: 4 block pairs before, 4 after, 0 new, 0 kept between blocks the change moved (ui_layout.py, whole screen, block depth 2)
Window overlaps: 0 not allowed after, 0 before, 0 new, 0 kept between windows the change moved, 0 standing; 1 allow-listed with the requester's words (hud-clusters.json windowOverlaps) (ui_layout.py, whole screen, open windows against the HUD and each other)
Alignment: max drift 0 px over the clusters (bottom-right HUD, top-left HUD); tolerance 2 px
Moved: 0 element move(s) over 4 px at 1920x1080 undocked, 1280x800 undocked, 1280x800 docked (ui_layout.py moves, the same save and screens before and after)
Pinned: 3 pin(s) in 3 census(es) (1920x1080 undocked, 1280x800 undocked, 1280x800 docked): 0 broken, 0 not shown (ui_layout.py pins, hud-pins.json: Station Info, building hover card, Player Inventory)
Colour: 0 loud fill(s), 0 state tint(s) bleeding into controls, 0 low-contrast text(s) over 6 still(s) (ui_look.py colour)
Critic: proofs/critic.md (pack 3f2a91ab, run 2): 6 stills, 2 broken or ugly found, 2 fixed, 0 open, 3 minor
Shape: 0 stretched, 0 mostly empty, 0 wall(s) of text over 3 census(es) (ui_layout.py shape)
Eye: 12 stills looked at full size, 0 look broken or poor (proofs/shots.md)
"""

    def body(self):
        return (HERE / "fixtures" / "pr-1251-deck-hub.md").read_text(encoding="utf-8")

    def test_1251_passes_without_its_files_and_fails_the_ui_rules_with_them(self):
        self.assertEqual([p for p in pe.check(self.body())[0] if "Real Deck" not in p], [])
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

    NOT_UI = ("Not UI: a world-space mesh (StationRouteArrowView draws one quad per arrow with "
              "Graphics.RenderMesh); no canvas, panel or HUD element changes\n")
    ARROW_FILES = ["Assets/Scripts/UI/World/StationRouteArrowView.cs", "Assets/Scripts/UI/World/StationRouteArrowFlow.cs",
                   "Assets/Scripts/UI/World/StationRouteArrowFlow.cs.meta"]

    def with_not_ui(self, line=None):
        return edit(GOOD, "Built player: yes\n", "Built player: yes\n" + (line or self.NOT_UI))

    def test_1604_a_world_space_arrow_under_ui_world_needs_no_layout_census_with_not_ui(self):
        """w1181 (#1604): the route arrow's speed fix touched UI/World scripts and failed every census line."""
        self.assertIn("UI change with no 'Content:' line", "\n".join(self.problems(GOOD, self.ARROW_FILES)))
        body = self.with_not_ui()
        self.assertEqual(self.problems(body, self.ARROW_FILES), [])
        self.assertIn("not UI", "\n".join(pe.check(body, self.ARROW_FILES)[1]))

    def test_1767_a_script_moved_into_ui_world_is_covered_by_not_ui(self):
        """w1767 (#2292): CircuitWirePresenter.cs moved from UI/Circuits/ to UI/World/; the deleted old path failed."""
        old, new = "Assets/Scripts/UI/Circuits/CircuitWirePresenter.cs", "Assets/Scripts/UI/World/CircuitWirePresenter.cs"
        files = [old, old + ".meta", new, new + ".meta"]
        moved = {old: ("D", 300), old + ".meta": ("D", 11), new: ("A", 570), new + ".meta": ("A", 11)}
        body = self.with_not_ui()
        self.assertEqual(pe.check(body, files, changes=moved)[0], [])
        # Deleted with nothing of that name added under UI/World/, or only modified: still a UI change.
        gone = {old: ("D", 300), new: ("A", 570), "Assets/Scripts/UI/Panels/Old.cs": ("D", 40)}
        self.assertIn("'Not UI:' covers only scripts under UI/World/",
                      "\n".join(pe.check(body, list(gone), changes=gone)[0]))
        edited = {old: ("M", 3), new: ("A", 570)}
        self.assertIn("'Not UI:' covers only scripts under UI/World/",
                      "\n".join(pe.check(body, list(edited), changes=edited)[0]))

    def test_not_ui_does_not_cover_a_panel_a_prefab_a_short_reason_or_kind_ui(self):
        body = self.with_not_ui()
        panel = self.ARROW_FILES + ["Assets/Scripts/UI/Panels/StationInfoPanel.cs"]
        self.assertIn("'Not UI:' covers only scripts under UI/World/", "\n".join(self.problems(body, panel)))
        prefab = ["Assets/Prefabs/UI/World/NameTag.prefab"]
        self.assertIn("'Not UI:' covers only scripts under UI/World/", "\n".join(self.problems(body, prefab)))
        short = self.with_not_ui("Not UI: a mesh\n")
        self.assertIn("'Not UI:' has to say why", "\n".join(self.problems(short, self.ARROW_FILES)))
        ui = edit(body, "Kind: visual, simulation", "Kind: ui, simulation")
        self.assertIn("contradict each other", "\n".join(self.problems(ui, self.ARROW_FILES)))

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
        overlap = "4 block pairs before, 5 after, 1 new, 0 kept between blocks the change moved (ui_layout.py)"
        self.assertIn("1 new overlap(s) between HUD blocks", self.reasons(self.ui_body(Overlaps=overlap)))
        kept = "1 block pairs before, 1 after, 0 new, 1 kept between blocks the change moved (ui_layout.py)"
        self.assertIn("keeps 1 overlap(s) between blocks the change moved", self.reasons(self.ui_body(Overlaps=kept)))
        old = "4 block pairs before, 4 after, 0 new (ui_layout.py, whole screen, block depth 2)"
        self.assertIn("how many overlaps were kept", self.reasons(self.ui_body(Overlaps=old)))
        drift = "max drift 14 px over the clusters (bottom-right HUD); tolerance 2 px"
        self.assertIn("'Alignment:' drifts 14 px", self.reasons(self.ui_body(Alignment=drift)))
        self.assertEqual(self.reasons(self.ui_body(Alignment="max drift 2 px over the clusters (bottom-right HUD)")), "")

    OPENED_OVERLAPS = ("4 block pairs before, 4 after, 0 new, 0 kept between blocks the change moved (ui_layout.py, whole "
                       "screen, block depth 2); 1 opened-panel pair(s) over the HUD, not counted here")
    OPENED_LINE = ("1 opened panel pair(s) over the HUD (allowed: Ben, w732 and w742), 0 under the HUD, 0 not clickable, "
                   "0 cut off by the screen edge, HUD restored on close: yes (3 covered HUD element(s) checked in closed.json)")

    def opened_body(self, line=None, **lines):
        body = self.ui_body(Overlaps=self.OPENED_OVERLAPS, **lines)
        return body if line is None else body.replace("Alignment:", f"Opened panels: {line}\nAlignment:", 1)

    def test_a_panel_the_player_opens_over_the_hud_passes_when_on_top_clickable_on_screen_and_restored(self):
        # w742 (Ben): "the blueprint panel showing over objectives is fine since its a temporarily opened panel"; w732: the
        # slide-out over the hotbar. Neither needs an 'intended' quote now.
        self.assertEqual(self.reasons(self.opened_body(self.OPENED_LINE)), "")

    def test_an_opened_panel_pair_needs_the_opened_panels_line(self):
        self.assertIn("no 'Opened panels:' line", self.reasons(self.opened_body()))

    def test_an_opened_panel_that_is_under_the_hud_or_not_clickable_or_cut_off_fails_without_an_intended_way_out(self):
        for bad, what in (("0 under the HUD", "1 under the HUD"), ("0 not clickable", "2 not clickable"),
                          ("0 cut off", "1 cut off")):
            line = self.OPENED_LINE.replace(bad, what) + ' intended (Ben): "anything"'
            self.assertIn("a panel the player opens may cover the HUD but must draw on top", self.reasons(self.opened_body(line)))

    def test_an_opened_panel_must_show_the_hud_back_on_close(self):
        line = self.OPENED_LINE.replace("restored on close: yes (3 covered HUD element(s) checked in closed.json)",
                                        "restored on close: not checked: pass --closed, a census taken after closing the panel")
        self.assertIn("does not show the HUD restored on close", self.reasons(self.opened_body(line)))
        no_order = self.OPENED_LINE + "; draw order not in the census: on-top and clickable NOT measured"
        self.assertIn("draw order was not measured", self.reasons(self.opened_body(no_order)))

    def test_1272_over_objectives_is_no_overlap_failure_but_its_colour_still_is(self):
        navy = ("GamePanels/BlueprintPanelChild/SolidBackdrop (new) vs GamePanels/InvAndCraft/InventoryPanel: delta E "
                "23.8 (on screen), alpha 0.98 vs 1.00, art 'flat fill' vs 'background-main'")
        reasons = self.reasons(self.opened_body(self.OPENED_LINE, Style=navy))
        self.assertNotIn("overlap", reasons)
        self.assertIn("delta E 23.8 from the classic panel", reasons)

    def test_1264s_drift_still_fails_beside_opened_panels(self):
        drift = "max drift 98 px over the clusters (bottom-right HUD, top-left HUD); tolerance 2 px"
        self.assertIn("'Alignment:' drifts 98 px", self.reasons(self.opened_body(self.OPENED_LINE, Alignment=drift)))

    def test_the_scene_counts_as_ui(self):
        self.assertTrue(pe.UI_PATH.search("Assets/Scenes/main.unity"))
        self.assertIn("no 'Overlaps:' line", self.reasons(GOOD, ["Assets/Scenes/main.unity"]))

    def test_an_old_copy_says_so_and_the_verdict_names_its_version(self):
        self.assertIn("ff-agents 1.20.44, but 1.21.0 is released", pe.stale_problem("1.20.44", "1.21.0"))
        self.assertIsNone(pe.stale_problem("1.22.0", "1.22.0"))
        self.assertIsNone(pe.stale_problem("1.22.0", None))
        self.assertIn("ff-agents 9.9.9", pe.verdict_text([], [], "9.9.9"))

    def test_a_stale_copy_never_posts_its_verdict(self):
        # w807: "this pr_evidence.py is ff-agents 1.24.18, but 1.24.21 is released" went onto a PR as a FAIL, twice
        stale = pe.stale_problem("1.24.18", "1.24.21")
        self.assertTrue(pe.comment_refused([stale]))
        self.assertTrue(pe.comment_refused(["a real problem", stale]))
        self.assertFalse(pe.comment_refused(["no 'Overlaps:' line"]))
        self.assertFalse(pe.comment_refused([]))


class CoveredTextTest(unittest.TestCase):
    """w727: a text whose drawn glyphs run under an opaque element of an opened screen is measured by ui_layout.py from the
    census `textRect`, not from RectTransform boxes."""

    ui_body = LayoutTest.ui_body
    reasons = LayoutTest.reasons

    def body(self, line):
        return re.sub(r"^Alignment:", lambda m: "Covered text: " + line + "\nAlignment:", self.ui_body(), count=1,
                      flags=re.MULTILINE)

    def test_a_new_covered_text_fails(self):
        self.assertIn("'Covered text:' has 1 new", self.reasons(self.body("1 text(s) of opened screens under an opaque element "
                                                                          "after, 0 before, 1 new (ui_layout.py)")))

    def test_none_new_passes_and_standing_ones_do_not_fail(self):
        self.assertEqual("", self.reasons(self.body("3 text(s) of opened screens under an opaque element after, 3 before, "
                                                    "0 new (ui_layout.py)")))

    def test_a_line_without_the_count_fails(self):
        self.assertIn("does not say how many covered texts are new", self.reasons(self.body("none found")))

    def test_a_census_without_text_bounds_is_not_clean(self):
        # "not measured" is a note, never a pass that reads as a measurement
        self.assertEqual("", self.reasons(self.body("0 text(s) of opened screens under an opaque element after, 0 before, 0 new "
                                                    "(ui_layout.py, drawn glyph bounds: needs `textRect`; NOT in this census: "
                                                    "not measured)")))


class WindowOverlapTest(unittest.TestCase):
    """w981: a window drawn over another window or the HUD is measured by ui_layout.py, not by eye. On the Deck's classic
    layout the Station strip stood 11 px over the Player Inventory (#1444, w961); `ui_layout.py overlaps` said 0 because it
    counted only always-on HUD blocks, and the w978 worker had to measure the rects by hand from the census."""

    ui_body = LayoutTest.ui_body
    reasons = LayoutTest.reasons

    LINE = ("0 not allowed after, 0 before, {new} new, {kept} kept between windows the change moved, {standing} standing; "
            "1 allow-listed with the requester's words (hud-clusters.json windowOverlaps) (ui_layout.py, whole screen)")
    BRIEF = 'Ben: "put the station panel controls above station info and it should be over the player inventory"'

    def line(self, new=0, kept=0, standing=0, extra=""):
        return self.LINE.format(new=new, kept=kept, standing=standing) + extra

    def body(self, **kw):
        body = self.ui_body()
        return re.sub(r"^Window overlaps:.*$", "Window overlaps: " + self.line(**kw), body, flags=re.MULTILINE)

    def test_a_ui_change_needs_the_window_overlaps_line(self):
        body = re.sub(r"^Window overlaps:.*\n", "", self.ui_body(), flags=re.MULTILINE)
        self.assertIn("no 'Window overlaps:' line", self.reasons(body))
        self.assertEqual(self.reasons(self.body()), "")

    def test_the_line_must_say_new_kept_and_standing(self):
        body = re.sub(r"^Window overlaps:.*$", "Window overlaps: 0 not allowed after", self.ui_body(), flags=re.MULTILINE)
        self.assertIn("does not say how many window overlaps are new, kept and standing", self.reasons(body))

    def test_the_strip_over_the_inventory_fails_new_or_kept(self):
        # 1444's case: the strip is new over the inventory; 1447's: the inventory moved and the overlap was kept
        self.assertIn("'Window overlaps:' has 1 new and 0 kept", self.reasons(self.body(new=1)))
        self.assertIn("'Window overlaps:' has 0 new and 1 kept", self.reasons(self.body(kept=1)))

    def test_intended_passes_only_with_words_found_in_the_brief(self):
        quote = ' intended (Ben): "put the station panel controls above station info and it should be over the player inventory"'
        body = self.body(new=1, extra=quote)
        self.assertEqual("\n".join(pe.check(body, None, self.BRIEF)[0]), "")
        self.assertIn("no brief to check the quote against", self.reasons(body))
        self.assertIn("not in the brief's quotations word for word",
                      "\n".join(pe.check(body, None, 'Ben: "move the inventory to the left"')[0]))

    def test_a_standing_overlap_is_a_note_not_a_failure(self):
        problems, notes = pe.check(self.body(standing=2))
        self.assertEqual(problems, [])
        self.assertTrue(any("2 window overlap(s) stand" in n for n in notes), notes)


class ShapeAndEyeTest(unittest.TestCase):
    """w1396: Ben, 2026-10-16, on stills a worker and an orchestrator had both passed: "the light panel is really messed up
    obviously" (w1386: the On/Off switch drawn as a 485x23 bar in the Deck dock; the shots sheet said "Same both sides")
    and "looks terrible. you can do better" (w1296: round 3 of a dialog with only its spacing nudged)."""

    # MEASURED (w1396): ui_layout.py shape on the w1386 tour's censuses of #1813's build, docked, 1920x1080 and 1280x800.
    W1386_SHAPE = ("1 stretched, 2 mostly empty, 0 wall(s) of text over 3 census(es) (ui_layout.py shape); walls of text "
                   "not measured (no `lines` in the census)")
    W1386_EYE = "16 stills looked at full size, 0 look broken or poor (proofs/shots.md: \"Same both sides\")"

    def reasons(self, **lines):
        return "\n".join(pe.check(LayoutTest().ui_body(**lines))[0])

    def test_w1386_as_measured_fails_on_the_stretched_switch_and_the_empty_panel(self):
        reasons = self.reasons(Shape=self.W1386_SHAPE)
        self.assertIn("'Shape:' has 1 stretched sprite(s)", reasons)
        self.assertIn("1 stretched", self.W1386_SHAPE)
        self.assertIn("2 mostly empty window(s)", reasons)

    def test_a_mostly_empty_window_passes_once_looked_at_and_explained(self):
        line = ("0 stretched, 1 mostly empty, 0 wall(s) of text over 3 census(es) (ui_layout.py shape); looked: the "
                "Cargo Hold of a 4-slot hold, its rows run the whole width, as on master")
        self.assertEqual(self.reasons(Shape=line), "")
        self.assertIn("2 mostly empty", self.reasons(Shape=self.W1386_SHAPE.replace("1 stretched", "0 stretched") +
                                                      "; looked: ok"))

    def test_a_stretched_sprite_passes_only_with_the_requesters_words(self):
        line = self.W1386_SHAPE.replace("2 mostly empty", "0 mostly empty")
        self.assertIn("stretched sprite", self.reasons(Shape=line + "; looked: it is a slider now"))
        self.assertEqual(self.reasons(Shape=line + '; intended (Ben): "make the switch a full-width bar"'), "")

    def test_no_shape_or_eye_line_fails(self):
        body = re.sub(r"^(Shape|Eye):.*\n", "", LayoutTest().ui_body(), flags=re.MULTILINE)
        reasons = "\n".join(pe.check(body)[0])
        self.assertIn("UI change with no 'Shape:' line", reasons)
        self.assertIn("UI change with no 'Eye:' line", reasons)

    # MEASURED (w1399): ui_look.py colour on a Windows build of #1817's round 2 against master's round 1, 1920x1080.
    W1334_COLOUR = ("1 loud fill(s), 1 state tint(s) bleeding into controls, 3 low-contrast text(s) over 1 still(s) "
                    "(ui_look.py colour); standing (on the before still too, not counted): 0 loud, 0 bleeding, 2 low-contrast")

    def test_w1334_round_two_as_measured_fails_on_its_colour_line(self):
        reasons = self.reasons(Colour=self.W1334_COLOUR)
        self.assertIn("'Colour:' has 1 loud fill(s), 1 state tint(s) bleeding into controls and 3 low-contrast", reasons)
        self.assertEqual(self.reasons(Colour=self.W1334_COLOUR + '; intended (Ben): "make the add stop button bright cyan"'),
                         "")

    def test_no_colour_or_critic_line_fails(self):
        body = re.sub(r"^(Colour|Critic):.*\n", "", LayoutTest().ui_body(), flags=re.MULTILINE)
        reasons = "\n".join(pe.check(body)[0])
        self.assertIn("UI change with no 'Colour:' line", reasons)
        self.assertIn("UI change with no 'Critic:' line", reasons)

    def test_a_critic_line_needs_its_pack_and_nothing_left_open(self):
        self.assertIn("names no pack id", self.reasons(Critic="critic.md: 6 stills, 2 broken or ugly found, 2 fixed, 0 open"))
        still_open = "critic.md (pack 3f2a91ab, run 1): 6 stills, 2 broken or ugly found, 1 fixed, 1 open, 0 minor"
        self.assertIn("1 broken or ugly finding(s) open", self.reasons(Critic=still_open))
        self.assertEqual(self.reasons(Critic=still_open + '; answered (Ben): "keep the orange edge, I like it"'), "")
        self.assertEqual(self.reasons(Critic=still_open + "; the menu card standing on master, filed as w1402"), "")
        self.assertIn("says how many stills", self.reasons(Critic="critic.md (pack 3f2a91ab): looked fine"))
        # w1399: the critic found real standing defects in master panels nobody had complained about; they are filed,
        # not fixed by the change that happened to show them.
        standing = "critic.md (pack 3f2a91ab, run 1): 3 stills, 4 broken or ugly found (2 standing), 2 fixed, 0 open, 3 minor"
        self.assertIn("2 standing finding(s)", self.reasons(Critic=standing))
        self.assertEqual(self.reasons(Critic=standing.replace("(2 standing)", "(2 standing, filed as w1405)")), "")

    def test_an_eye_line_needs_its_counts(self):
        self.assertIn("'Eye:' says how many stills", self.reasons(Eye="looked at them all, fine"))

    def test_a_still_that_looks_broken_fails_unless_filed_as_standing(self):
        self.assertIn("1 still(s) that look broken or poor",
                      self.reasons(Eye="16 stills looked at full size, 1 look broken or poor (docked lamp: switch is a bar)"))
        self.assertEqual(self.reasons(Eye="16 stills looked at full size, 1 look broken or poor (docked lamp: the switch "
                                          "drawn as a bar, standing on master, filed as w1397)"), "")


class MovedTest(unittest.TestCase):
    """w826 and w894: a UI change lists every HUD element it moved, at 1920x1080 and at 1280x800 undocked and docked, and
    each one is asked for in the requester's own words. Four corrections from Ben: w722/w723 pushed the objectives card
    under the Station strip ("you did more with the overall layout than i wanted"); #1282 moved Station Info to the top
    left ("i didnt tell you to move that"); the dock kept Station Info and the building hover card stacked top left
    ("it seems like you keep moving it to the top on the deck. I don't want that"; "put it back over the minimap, stop
    moving panels around that I don't ask you to move around")."""

    FILES_1282 = (HERE / "fixtures" / "pr-1282-classic-deck.files").read_text(encoding="utf-8").split()
    HEAD = ("Moved: 2 element move(s) over 4 px at 1920x1080 undocked, 1280x800 undocked, 1280x800 docked (ui_layout.py "
            "moves, the same save and screens before and after)")
    # MEASURED (w826): editor censuses at 4762a5bc3 (develop before #1282) and 102e46bed (#1282 merged).
    BIG = ("- 1920x1080 undocked GamePanels/BuildInfoPanel: x -312, y -736 px, size +201 x -37 px (was 874,777 173x128, "
           "now 461,59 374x92): ")
    DECK = ("- 1280x800 undocked GamePanels/BuildInfoPanel: x -30, y -476 px, size +190 x -35 px (was 558,515 163x121, now "
            "434,56 352x86): ")
    DECK_QUOTE = ('asked (Ben): "we need a new place for Station Info hover panel thing it takes up too much space in the '
                  'steam deck ui"')
    BRIEF = ("Ben adds: \"we need a new place for Station Info hover panel thing it takes up too much space in the steam "
             "deck ui, maybe put it in two columns? but make sure it can handle variation in text length\"")
    STRIP = ("- 1280x800 docked GamePanels/StructuredStation: x +720, y +629 px (was 10,59 432x112, now 759,699 374x90): "
             'asked (Ben): "maybe just down where the old copy and deconstruct buttons were next to the abilities"')

    def body(self, moved, pinned=None):
        lines = LayoutTest().ui_body()
        lines = re.sub(r"^Moved:.*$", lambda _: moved, lines, flags=re.MULTILINE)
        if pinned is not None:
            lines = re.sub(r"^Pinned:.*$", lambda _: pinned, lines, flags=re.MULTILINE)
        return lines

    def reasons(self, moved, brief=None, pinned=None):
        return "\n".join(pe.check(self.body(moved, pinned), None, brief)[0])

    def fixture(self, name):
        return (HERE / "fixtures" / name).read_text(encoding="utf-8")

    def test_1282_as_written_fails_for_its_missing_moved_and_pinned_lines(self):
        reasons = "\n".join(pe.check(self.fixture("pr-1282-classic-deck.md"), self.FILES_1282)[0])
        self.assertIn("no 'Moved:' line", reasons)
        self.assertIn("no 'Pinned:' line", reasons)

    def test_no_move_on_every_screen_passes_and_the_docked_layout_is_required(self):
        self.assertEqual(self.reasons(next(x for x in UiTest.UI_LINES.splitlines() if x.startswith("Moved:"))), "")
        reasons = self.reasons("Moved: 0 element move(s) over 4 px at 1920x1080, 1280x800 (ui_layout.py check, the same "
                               "save and screens before and after)")
        self.assertIn("'Moved:' does not cover 1280x800 undocked, 1280x800 docked", reasons)

    def test_an_unmarked_move_fails(self):
        reasons = self.reasons("\n".join([self.HEAD, self.BIG + "mark: ?", self.DECK + "mark: ?"]))
        self.assertIn("'Moved:' 1920x1080 undocked GamePanels/BuildInfoPanel is not marked", reasons)
        self.assertIn("counts 2 move(s) but only 0", reasons)

    def test_1282_would_have_been_caught_on_the_desktop_with_the_deck_quote(self):
        reasons = self.reasons("\n".join([self.HEAD, self.BIG + self.DECK_QUOTE, self.DECK + self.DECK_QUOTE]), self.BRIEF)
        self.assertIn("1920x1080 undocked GamePanels/BuildInfoPanel: the quote asks for the Deck", reasons)
        self.assertNotIn("1280x800 undocked GamePanels/BuildInfoPanel: the quote", reasons)

    def test_not_asked_justified_no_longer_passes(self):
        # w894: #1397 marked Station Info and the hover card "not asked: justified" in the dock and got a PASS.
        moved = "\n".join([self.HEAD, self.BIG + "not asked: justified: the hover card now covers that spot at 1920x1080",
                           self.DECK + self.DECK_QUOTE])
        self.assertIn("is marked not asked: justified", self.reasons(moved, self.BRIEF))

    def test_1397_as_written_fails_on_its_justified_moves_and_its_folded_line(self):
        body = self.fixture("pr-1397-station-controls.md")
        files = self.fixture("pr-1397-station-controls.files").split()
        reasons = "\n".join(pe.check(body, files, self.fixture("brief-w873.txt"))[0])
        self.assertIn("MiniInventory, HoverDescription and BuildInfoPanel (docked) is marked not asked: justified", reasons)
        self.assertIn("one element per line", reasons)
        self.assertIn("no 'Pinned:' line", reasons)
        self.assertNotIn("StructuredStation (docked): the quote is not in the brief", reasons)

    def test_1392s_quotes_that_are_not_bens_words_fail_against_its_brief(self):
        body = self.fixture("pr-1392-panel-cluster.md")
        reasons = "\n".join(pe.check(body, None, self.fixture("brief-w878.txt"))[0])
        self.assertIn("StationGridEntityPanel: the quote is not in the brief's quotations", reasons)
        self.assertIn("DefensePlatformEntityPanel (its Range window): the quote is not in the brief's quotations", reasons)
        self.assertNotIn("MiniInventory: the quote is not in the brief", reasons)

    def test_a_quote_needs_a_brief_and_must_be_in_its_quotations(self):
        moved = "\n".join([self.HEAD.replace("2 element", "1 element"), self.STRIP])
        self.assertIn("no brief to check the quote against", self.reasons(moved))
        self.assertEqual(self.reasons(moved, self.fixture("brief-w873.txt")), "")
        in_body = moved + '\nBrief (Ben): "maybe just down where the old copy and deconstruct buttons were next to the abilities"'
        self.assertEqual(self.reasons(in_body), "")
        brief = ('Ben decided the fixed spot: "for the station controls panel just put in the top left corner". Mind the '
                 'top-left HUD (the health bar and the objectives) so nothing overlaps.')
        card = ("- 1280x800 undocked GamePanels/ObjectivesPanel: x +0, y +69 px (was 10,120 410x160, now 10,189 410x160): "
                'asked (Ben): "Mind the top-left HUD (the health bar and the objectives) so nothing overlaps"')
        self.assertIn("not in the brief's quotations", self.reasons("\n".join([self.HEAD.replace("2 element", "1 element"), card]),
                                                                    brief))

    def test_a_pinned_element_moves_only_when_the_quote_names_it(self):
        head = self.HEAD.replace("2 element", "1 element")
        brief = 'Ben: "put the panels in a tidy cluster at the top left" and "the station info box goes under the strip"'
        cluster = ("- 1280x800 docked GamePanels/BuildInfoPanel: x +0, y -119 px (was 140,297 284x86, now 140,178 284x86): "
                   'asked (Ben): "put the panels in a tidy cluster at the top left"')
        self.assertIn("is pinned (Station Info", self.reasons("\n".join([head, cluster]), brief))
        named = cluster.replace("put the panels in a tidy cluster at the top left", "the station info box goes under the strip")
        self.assertNotIn("is pinned", self.reasons("\n".join([head, named]), brief))

    def test_2269s_pinned_panels_only_got_shorter_and_pass_on_bens_words(self):
        # w1824: #2269 (w1814, the CJK font fix) made the hover card and Station Info 5 to 8 px shorter in ja/ko/zh/ru/uk,
        # left, right and bottom edges kept. Ben had answered: "Fix it at the fonts; a few pixels shorter in those
        # languages is fine." ff-agents 1.30.10 failed its 20 pinned lines because the quote names neither panel, and the
        # worker had to ask him again. MEASURED: the PR's Moved block as posted, 2026-10-22.
        brief, moved = self.fixture("pr-2269-cjk-fonts-moved.txt").split("\n", 1)
        self.assertEqual(self.reasons(moved.strip(), brief), "")
        # The quote still has to be the requester's words.
        self.assertIn("HoverDescription (ja): the quote is not in the brief's quotations",
                      self.reasons(moved.strip(), 'Ben: "make the fonts bigger"'))

    def test_a_pinned_element_that_moves_while_it_resizes_still_needs_its_name(self):
        head = self.HEAD.replace("2 element", "1 element")
        brief = 'Ben: "Fix it at the fonts; a few pixels shorter in those languages is fine."'
        quote = 'asked (Ben): "Fix it at the fonts; a few pixels shorter in those languages is fine."'
        cases = {
            # shorter, and taken up the screen into the cluster: the bottom edge left the abilities
            "taken up": "x +0, y -119 px, size +0 x -8 px (was 823,791 274x100, now 823,668 274x92)",
            # the same height, shifted 6 px: a move, not a resize
            "shifted": "x +0, y +6 px (was 823,791 274x100, now 823,797 274x100)",
            # shorter and wider: the width is part of where the panel sits over its anchor
            "wider": "x -20, y +4 px, size +40 x -8 px (was 823,791 274x100, now 803,799 314x92)",
            # shorter about its middle by more than the census's move threshold at the bottom edge
            "much shorter": "x +0, y +0 px, size +0 x -40 px (was 823,791 274x100, now 823,811 274x60)",
        }
        for why, rect in cases.items():
            line = f"- 1920x1080 undocked GamePanels/BuildInfoPanel (ja): {rect}: {quote}"
            self.assertIn("is pinned (Station Info", self.reasons("\n".join([head, line]), brief), why)
        kept = f"- 1920x1080 undocked GamePanels/BuildInfoPanel (ja): x +0, y +4 px, size +0 x -8 px (was 823,791 274x100, now 823,799 274x92): {quote}"
        self.assertNotIn("is pinned", self.reasons("\n".join([head, kept]), brief))

    def test_a_broken_or_unmeasured_pin_fails_with_no_way_out(self):
        moved = next(x for x in UiTest.UI_LINES.splitlines() if x.startswith("Moved:"))
        broken = ("Pinned: 3 pin(s) in 3 census(es) (1920x1080 undocked, 1280x800 undocked, 1280x800 docked): 2 broken, 0 "
                  'not shown (ui_layout.py pins); intended (Ben): "anything"')
        self.assertIn("2 broken pin(s)", self.reasons(moved, pinned=broken))
        unseen = broken.replace("2 broken, 0 not shown", "0 broken, 3 not shown")
        self.assertIn("3 pin(s) not shown", self.reasons(moved, pinned=unseen))
        classic = "Pinned: 3 pin(s) in 2 census(es) (1920x1080 undocked, 1280x800 undocked): 0 broken, 0 not shown"
        self.assertIn("'Pinned:' does not cover 1280x800 docked", self.reasons(moved, pinned=classic))

    def test_a_reverted_move_does_not_count(self):
        moved = "\n".join([self.HEAD, self.BIG + "not asked: reverted in 3f2a1b0", self.STRIP])
        self.assertIn("counts 2 move(s) but only 1", self.reasons(moved, self.fixture("brief-w873.txt")))
        retaken = self.HEAD.replace("2 element", "1 element")
        self.assertEqual(self.reasons("\n".join([retaken, self.BIG + "not asked: reverted in 3f2a1b0", self.STRIP]),
                                      self.fixture("brief-w873.txt")), "")


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
        self.assertTrue([p for p in problems if "without flicker" in p and "Close-ups" in p], problems)
        problems = without_closeups(problems)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("AsteroWorldSprite.ShaderGraph with no '## Used by' section", problems[0])
        self.assertEqual(without_closeups(pe.check(self.body("pr-1068-alt-icon-backing.md"),
                                                   [f for f in self.FILES_1068 if "Art/Shaders" not in f])[0]), [])

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


class BalanceTest(unittest.TestCase):
    """w1440: enemy, combat or spawn numbers move the difficulty curve; the PR shows the balance stages before and
    after. Build 108 (0.50.0.108) shipped camp expansion's numbers with no such run, and a late-game base met about
    three raids a second (w1439)."""

    FILES = ["Assets/Resources/GlobalConfig.asset", "Assets/Scripts/FFSystems/EnemyCamps/EnemyCampExpansionSystem.cs"]
    BALANCE = """
## Balance

Stages: BAL-mid-lifeastwo, BAL-end-justplay, BAL-end-meltcpu on players of 1a2b3c4 (before) and 5d6e7f8 (after)

| metric | before (BAL-end-justplay-frontier) | after (BAL-end-justplay-frontier) | after / before |
|---|---:|---:|---:|
| raids / h | 10,800 | 240 | 0.02 |

Flags: none on the after build
Baseline: BAL-end-justplay-frontier's raidsPerHour and threatHpPerHour moved to the after run, the fix's own numbers
"""

    def test_a_balance_change_without_the_section_fails(self):
        problems = pe.check(GOOD, self.FILES)[0]
        self.assertTrue(any("no '## Balance' section" in p for p in problems), problems)

    def test_the_section_with_its_table_passes(self):
        self.assertEqual(pe.check(GOOD + self.BALANCE, self.FILES)[0], [])

    def test_a_missing_table_or_flags_line_fails(self):
        problems = pe.check(GOOD + self.BALANCE.replace("| metric | before", "| m | b"), self.FILES)[0]
        self.assertTrue(any("before/after table" in p for p in problems), problems)
        problems = pe.check(GOOD + self.BALANCE.replace("Flags: none on the after build\n", ""), self.FILES)[0]
        self.assertTrue(any("'Flags:' line" in p for p in problems), problems)

    def test_no_curve_change_needs_a_reason(self):
        reasoned = "\n## Balance\n\nNo curve change: telemetry log lines only, read by nothing in the simulation\n"
        self.assertEqual(pe.check(GOOD + reasoned, self.FILES)[0], [])
        problems = pe.check(GOOD + "\n## Balance\n\nNo curve change: none\n", self.FILES)[0]
        self.assertTrue(problems)

    def test_other_files_need_no_section(self):
        self.assertEqual(pe.check(GOOD, ["Assets/Scripts/FFSystems/Crafting/CrafterSystem.cs"])[0], [])
        self.assertTrue(pe.BALANCE_PATH.search("Assets/Resources/ItemConfig/RazorSpawnerConfig.asset"))
        self.assertFalse(pe.BALANCE_PATH.search("Assets/Resources/ItemConfig/IronOreConfig.asset"))


class ArtLanguageTest(unittest.TestCase):
    """w1241, w1332: Ben's second correction of one kind. A comet's catch effect shipped turning rings round the head
    (v1) and was turned down: "again I don't like the unnatural circle effect that looks like UI. The vfx should be part
    of the game world in its appearance." Effect art says what it was compared with and that it draws no ring."""

    def body(self):
        return (HERE / "fixtures" / "pr-1816-comet-catch-tail.md").read_text(encoding="utf-8")

    def files(self):
        return (HERE / "fixtures" / "pr-1816-comet-catch-tail.files").read_text(encoding="utf-8").split()

    def with_line(self, line):
        return edit(self.body(), "Built player: yes", line + "\nBuilt player: yes")

    def test_1816_as_merged_fails_only_on_the_missing_art_language_line(self):
        problems = without_closeups(pe.check(self.body(), self.files())[0])
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("no 'Art language:' line", problems[0])

    def test_a_line_naming_the_reference_and_no_ring_passes(self):
        good = self.with_line("Art language: compared with the Railgun's glow and master's comet in the same stills; "
                              "no ring, circle or UI-like overlay: in-world light, debris streaks and the catcher's own glow")
        self.assertEqual(without_closeups(pe.check(good, self.files())[0]), [])

    def test_v1_rings_fail(self):
        rings = self.with_line("Art language: compared with master's comet; two containment rings turn round the head")
        self.assertIn("draws no ring", "\n".join(pe.check(rings, self.files())[0]))

    def test_an_indicator_the_person_asked_for_passes(self):
        asked = self.with_line('Art language: compared with the Alt-view icons; Ben asked for one (Ben): "give the target a '
                               'ring so I can see it"')
        self.assertEqual(without_closeups(pe.check(asked, self.files())[0]), [])

    def test_a_script_or_icon_change_needs_no_line(self):
        problems = pe.check(self.body(), ["Assets/Scripts/FFSystems/Presentation/CometVfxPresentationSystem.cs",
                                          "Assets/Art/Shaders/AltIconSprite.ShaderGraph"])[0]
        self.assertFalse([p for p in problems if "Art language" in p], problems)


HERO_LINE = ("Hero art: concepts: shots/concept-a-tether.png, shots/concept-b-fold.png, shots/concept-c-lattice.png shown to "
             "Ben, he picked B; detail: compared with the Railgun and the Advanced Assembler in one still "
             "(shots/detail-side-by-side.png); differs: from the Railgun's slug and the Plasma Bolt's orb in "
             "shots/impact-vs-weapons.png, no reuse of their effects; distinct: a tether of purple light that pulls the "
             "target in and folds the hull inward; cost: measured 0.4 ms GPU, 62 fps in the built player with 12 firing")


class HeroArtTest(unittest.TestCase):
    """w1497: Ben turned down generic new art three times on 2026-10-18 (w1470 Singularity Lance, w1466 Urso Ballista,
    w1475 Shield Generator effect). A pull request that adds a model or effect art carries a filled 'Hero art:' line."""

    def fixture(self, name):
        return pe.parse_files_file((HERE / "fixtures" / f"{name}.files").read_text(encoding="utf-8"))

    def run_check(self, line, name="pr-1929-urso-ballista"):
        files, changes = self.fixture(name)
        body = GOOD if line is None else edit(GOOD, "Looked: yes", line + "\nLooked: yes")
        found = pe.check(body, files, changes=changes)
        return [p for p in found[0] if "Hero art" in p or "hero art" in p.lower() or "new model or effect" in p], found[1]

    def test_the_real_prs_of_the_three_corrections_are_hero_art(self):
        for name in ("pr-1921-singularity-lance", "pr-1929-urso-ballista", "pr-1924-shield-generator"):
            files, changes = self.fixture(name)
            self.assertTrue(pe.hero_art_files(files, changes), name)

    def test_a_missing_line_fails_and_names_the_files(self):
        problems, _ = self.run_check(None)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("no 'Hero art:' line", problems[0])
        self.assertIn("urso-ballista", problems[0])

    def test_a_filled_line_passes(self):
        for name in ("pr-1921-singularity-lance", "pr-1929-urso-ballista", "pr-1924-shield-generator"):
            problems, notes = self.run_check(HERO_LINE, name)
            self.assertEqual(problems, [], (name, problems))
            self.assertTrue([n for n in notes if n.startswith("hero art:")])

    def test_a_line_on_several_lines_passes(self):
        text = HERO_LINE.replace("; detail:", "\n  - detail:").replace("; differs:", "\n  - differs:") \
                        .replace("; distinct:", "\n  - distinct:").replace("; cost:", "\n  - cost:")
        self.assertEqual(self.run_check(text)[0], [])

    def test_placeholder_lines_fail(self):
        for line in ("Hero art: TBD", "Hero art: done", "Hero art: yes, see the PR",
                     "Hero art: concepts: <stills>; detail: <compared with>; differs: <how>; distinct: <why>; cost: <ms>",
                     HERO_LINE.replace("cost: measured 0.4 ms GPU, 62 fps in the built player with 12 firing", "cost: TBD"),
                     HERO_LINE.replace("distinct: a tether of purple light that pulls the target in and folds the hull inward",
                                       "distinct: todo, write this later in the evidence")):
            self.assertTrue(self.run_check(line)[0], line)

    def test_each_part_is_needed(self):
        for part in ("concepts", "detail", "differs", "distinct", "cost"):
            cut = re.sub(rf"; {part}:[^;]*", "", HERO_LINE) if part != "concepts" else re.sub(
                r"concepts:[^;]*; ", "", HERO_LINE)
            problems = self.run_check(cut)[0]
            self.assertTrue(any(f"no '{part[:7] if part != 'concepts' else 'concept'}" in p or part[:6] in p for p in problems),
                            (part, problems))

    def test_one_concept_or_no_pick_fails(self):
        one = HERO_LINE.replace("shots/concept-b-fold.png, shots/concept-c-lattice.png ", "")
        self.assertIn("at least two concept", "\n".join(self.run_check(one)[0]))
        unpicked = HERO_LINE.replace("he picked B", "all three look fine")
        self.assertIn("which concept was picked", "\n".join(self.run_check(unpicked)[0]))

    def test_a_detail_comparison_without_a_named_reference_or_still_fails(self):
        vague = HERO_LINE.replace("compared with the Railgun and the Advanced Assembler in one still "
                                  "(shots/detail-side-by-side.png)", "looks detailed enough, compared by eye")
        self.assertIn("'Hero art' detail", "\n".join(self.run_check(vague)[0]))

    def test_reuse_of_another_weapons_effect_must_be_said(self):
        silent = HERO_LINE.replace(", no reuse of their effects", ", the colours are different")
        self.assertIn("'Hero art' differs", "\n".join(self.run_check(silent)[0]))
        called_out = HERO_LINE.replace("no reuse of their effects", "reuses the Plasma Bolt's trail, recoloured")
        self.assertEqual(self.run_check(called_out)[0], [])

    def test_the_frame_cost_is_measured_with_a_unit(self):
        words = HERO_LINE.replace("measured 0.4 ms GPU, 62 fps in the built player with 12 firing", "cheap, runs fine")
        self.assertIn("measured frame cost", "\n".join(self.run_check(words)[0]))
        guess = HERO_LINE.replace("measured 0.4 ms GPU, 62 fps in the built player with 12 firing", "expected about 0.5 ms")
        self.assertIn("not estimated", "\n".join(self.run_check(guess)[0]))

    def test_n_a_with_a_reason_a_reviewer_can_see_passes_with_a_note(self):
        files = ["Assets/Resources/Vfx/StationShieldMaterial.mat"]
        changes = {files[0]: ("M", 120)}
        body = edit(GOOD, "Looked: yes", "Hero art: n/a (a bug fix: the material lost its tint after a shader rename)\nLooked: yes")
        problems, notes = pe.check(body, files, changes=changes)
        self.assertEqual([p for p in problems if "Hero art" in p], [], problems)
        self.assertTrue([n for n in notes if n.startswith("HERO ART SKIPPED")], notes)

    def test_n_a_without_a_reason_or_for_new_art_fails(self):
        for line in ("Hero art: n/a", "Hero art: n/a (not needed)", "Hero art: n/a (trust me, it looks great already)"):
            self.assertTrue(self.run_check(line)[0], line)
        added = self.run_check("Hero art: n/a (a bug fix, nothing new is drawn by the added model)")[0]
        self.assertIn("added files", "\n".join(added))
        self.assertEqual(self.run_check("Hero art: n/a (a re-export of the same model after a rename)")[0], [])

    def test_what_is_not_hero_art_needs_no_line(self):
        small_tweak = {"Assets/Resources/Vfx/StationShieldMaterial.mat": ("M", 12)}
        edited_model = {"Assets/Art/Content/Railgun/railgun-lowpoly.fbx": ("M", 0)}
        icon = {"Assets/Resources/Icons/ShieldGenerator.png": ("A", 3), "Assets/UI/ShieldIcon.mat": ("A", 20)}
        pack = {"Assets/SineVFX/TopDownEffects/Shaders/Foo.shader": ("A", 300),
                "Assets/ExternalAssets/Ship/ship.fbx": ("A", 0)}
        code = {"Assets/Scripts/FFSystems/Presentation/ProjectileParticlePresentationSystem.cs": ("M", 86)}
        for changes in (small_tweak, edited_model, icon, pack, code):
            self.assertEqual(pe.hero_art_files(list(changes), changes), [], changes)
        big_rework = {"Assets/Art/Shaders/Vfx/VfxComet.shader": ("M", 369)}
        self.assertTrue(pe.hero_art_files(list(big_rework), big_rework))

    def test_a_plain_file_list_counts_a_model_but_not_an_edited_shader(self):
        self.assertTrue(pe.hero_art_files(["Assets/Art/Content/X/x.fbx"]))
        self.assertFalse(pe.hero_art_files(["Assets/Art/Shaders/Vfx/VfxComet.shader"]))

    def test_the_old_1816_fixture_is_unchanged_by_the_new_check(self):
        body = (HERE / "fixtures" / "pr-1816-comet-catch-tail.md").read_text(encoding="utf-8")
        files = (HERE / "fixtures" / "pr-1816-comet-catch-tail.files").read_text(encoding="utf-8").split()
        problems = pe.check(body, files)[0]
        self.assertFalse([p for p in problems if "Hero art" in p], problems)

    def test_name_status_file_lists_parse(self):
        files, changes = pe.parse_files_file("A\tAssets/a b/x.fbx\nM\tAssets/y.mat\t57\nR100\told.mat\tAssets/new.mat\nplain.txt\n")
        self.assertEqual(files, ["Assets/a b/x.fbx", "Assets/y.mat", "Assets/new.mat", "plain.txt"])
        self.assertEqual(changes["Assets/y.mat"], ("M", 57))
        self.assertEqual(changes["Assets/a b/x.fbx"][0], "A")


SCALE_LINE = ("Scale: shots/repair-pack-on-connector.png, shots/repair-pack-inserter-hand.png: the Repair Pack beside "
              "Iron Plates and Circuits on the same connector and in the same inserter hand, at gameplay zoom in the "
              "built player; its size matches theirs (0.9x an Iron Plate's width)")


class ScaleTest(unittest.TestCase):
    """w2204: #1596's Repair Pack shipped far too big on connectors (Ben: "the repair pack connector item is comically
    large"). A pull request that adds or changes a world model names a built-game still of it beside its neighbours."""

    def fixture(self, name):
        return pe.parse_files_file((HERE / "fixtures" / f"{name}.files").read_text(encoding="utf-8"))

    def run_check(self, line, name="pr-1596-repair-pack"):
        files, changes = self.fixture(name)
        body = GOOD if line is None else edit(GOOD, "Looked: yes", line + "\nLooked: yes")
        found = pe.check(body, files, changes=changes)
        return [p for p in found[0] if "Scale" in p or "world model" in p], found[1]

    def test_the_repair_pack_pr_is_a_scale_change_and_its_icon_is_not(self):
        files, changes = self.fixture("pr-1596-repair-pack")
        self.assertEqual(pe.scale_files(files, changes), [
            "Assets/Art/Content/RepairPack/RepairPack.asset",
            "Assets/Resources/ConnectorEntities/RepairPackConnectorItem.prefab",
            "Assets/Resources/ItemEntities/RepairPack.prefab"])

    def test_the_repair_pack_pr_without_a_scale_line_fails(self):
        problems, _ = self.run_check(None)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("no 'Scale:' line", problems[0])
        self.assertIn("RepairPack.asset", problems[0])
        self.assertIn("on a connector and in an inserter hand", problems[0])

    def test_a_filled_line_passes_with_a_note(self):
        problems, notes = self.run_check(SCALE_LINE)
        self.assertEqual(problems, [])
        self.assertTrue([n for n in notes if n.startswith("scale:")], notes)

    def test_each_part_is_needed(self):
        for cut, expect in (
                ("shots/repair-pack-on-connector.png, shots/repair-pack-inserter-hand.png: ", "names no still"),
                (" in the built player", "built player"),
                ("beside Iron Plates and Circuits ", "what the model is beside"),
                (" at gameplay zoom", "zoom"),
                ("; its size matches theirs (0.9x an Iron Plate's width)", "no verdict"),
                ((" and in the same inserter hand", ", shots/repair-pack-inserter-hand.png"), "in an inserter hand: an item")):
            line = SCALE_LINE
            for piece in (cut,) if isinstance(cut, str) else cut:
                line = line.replace(piece, "")
            problems = self.run_check(line)[0]
            self.assertTrue(any(expect in p for p in problems), (cut, problems))

    def test_a_still_on_its_own_or_in_the_editor_fails(self):
        for line in ("Scale: shots/repair-pack.png, the model on its own in the prefab preview, looks right",
                     "Scale: TBD", "Scale: checked"):
            self.assertTrue(self.run_check(line)[0], line)

    def test_a_structure_needs_no_connector_or_inserter(self):
        changes = {"Assets/Art/Content/Warden/warden.fbx": ("A", 3)}
        line = ("Scale: shots/warden-fleet.png: the Warden beside a Cargo Barge and two Fighters at gameplay zoom in the "
                "built player; it reads 1.2x a Fighter, as designed")
        body = edit(GOOD, "Looked: yes", line + "\nLooked: yes")
        self.assertEqual([p for p in pe.check(body, list(changes), changes=changes)[0] if "Scale" in p], [])

    def test_n_a_with_a_reason_passes_for_a_retint_and_fails_for_new_art(self):
        problems, notes = self.run_check("Scale: n/a (a re-tint: only the body material's colour changed, size unchanged)",
                                         "pr-2309-hyper-assembler-teal")
        self.assertEqual(problems, [])
        self.assertTrue([n for n in notes if n.startswith("SCALE SKIPPED")], notes)
        self.assertTrue(self.run_check("Scale: n/a", "pr-2309-hyper-assembler-teal")[0])
        added = self.run_check("Scale: n/a (a re-tint of the material, the size is unchanged)")[0]
        self.assertIn("added files", "\n".join(added))

    def test_what_is_not_a_world_model_needs_no_line(self):
        files, changes = self.fixture("pr-1987-map-icons")
        self.assertEqual(pe.scale_files(files, changes), [], "70 edited prefabs for map icons are not a new model")
        other = {"Assets/Resources/Icons/RepairPack.png": ("A", 3), "Assets/Art/ItemArt/Icons/Foo.fbx": ("A", 3),
                 "Assets/Art/Content/Effects/SmallEnergyBeam/beam.fbx": ("A", 3), "Assets/Art/Shaders/Vfx/X.asset": ("A", 9),
                 "Assets/Resources/ItemConfig/RepairPack.asset": ("A", 1161), "Assets/ExternalAssets/Ship/ship.fbx": ("A", 0),
                 "Assets/Resources/ItemEntities/Old.prefab": ("D", 300), "Assets/UI/Panels/Foo.prefab": ("A", 90)}
        self.assertEqual(pe.scale_files(list(other), other), [])

    def test_the_note_asks_the_critic_about_scale(self):
        self.assertTrue(any("in scale with its neighbours" in q for q in pe.scale_questions(SCALE_LINE)))
        self.assertEqual(pe.scale_questions("Close-ups: z-fight: edge.png"), [])


CENSUS_LINE = ("Hidden census: shots/f7-census.json, clips/f7-hidden.mp4: with a flying station hidden (F7) in the built "
               "player, 0 renderers, particle systems and VFX still drawn inside its bounds; it carries its children, the "
               "hover field VFX, beams, shields, engine flames, lamp lights, belt items and its outline")


class HiddenCensusTest(unittest.TestCase):
    """w2210: Hide Flying Stations was fixed one leftover at a time (belt items, then the hover field, then shields and
    engines; Ben: "and anything else, you keep missing stuff"). A hide change counts what is still drawn, in a built game."""

    def fixture(self, name):
        return pe.parse_files_file((HERE / "fixtures" / f"{name}.files").read_text(encoding="utf-8"))

    def run_check(self, line, name="pr-2345-hover-field-hidden"):
        files, changes = self.fixture(name)
        body = GOOD if line is None else edit(GOOD, "Looked: yes", line + "\nLooked: yes")
        found = pe.check(body, files, changes=changes)
        return [p for p in found[0] if "Hidden census" in p or "hide or visibility" in p], found[1]

    def test_the_hover_field_pr_is_a_hide_change(self):
        files, changes = self.fixture("pr-2345-hover-field-hidden")
        self.assertEqual(pe.hide_files(files, changes),
                         ["Assets/Scripts/FFSystems/Presentation/FlyingStationVisibilitySystem.cs"])

    def test_the_hover_field_pr_without_a_census_fails(self):
        problems, _ = self.run_check(None)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("no 'Hidden census:' line", problems[0])
        self.assertIn("FlyingStationVisibilitySystem.cs", problems[0])

    def test_a_filled_census_passes_with_a_note(self):
        problems, notes = self.run_check(CENSUS_LINE)
        self.assertEqual(problems, [])
        self.assertTrue([n for n in notes if n.startswith("hidden census:")], notes)

    def test_each_part_is_needed(self):
        for cut, expect, new in (
                ("shots/f7-census.json, clips/f7-hidden.mp4: ", "names no clip", ""),
                (" in the built player", "built player", ""),
                (" inside its bounds", "where it counted", ""),
                ("0 renderers, particle systems and VFX still drawn", "no count", "it all looks hidden"),
                ("0 renderers", "counts 2 still drawn", "2 renderers"),
                ("; it carries its children, the hover field VFX, beams, shields, engine flames, lamp lights, belt items "
                 "and its outline", "what the thing carries", "")):
            problems = self.run_check(CENSUS_LINE.replace(cut, new))[0]
            self.assertTrue(any(expect in p for p in problems), (cut, problems))

    def test_a_hand_list_or_placeholder_fails(self):
        for line in ("Hidden census: hid the shields and the engines too", "Hidden census: TBD", "Hidden census: n/a"):
            self.assertTrue(self.run_check(line)[0], line)

    def test_n_a_with_a_reason_passes_for_a_selection_change(self):
        problems, notes = self.run_check("Hidden census: n/a (selection and box drags only skip hidden stations; nothing "
                                         "drawn changes)", "pr-1836-hidden-station-selection")
        self.assertEqual(problems, [])
        self.assertTrue([n for n in notes if n.startswith("HIDDEN CENSUS SKIPPED")], notes)

    def test_ui_lobby_and_probe_hides_need_no_census(self):
        files, changes = self.fixture("pr-2207-hud-hide-while-covered")
        self.assertEqual(pe.hide_files(files, changes), [], "a HUD piece hiding under a window is not a world hide")
        other = {"Assets/Scripts/UI/World/MapMarkerVisibility.cs": ("A", 9),
                 "Assets/Scripts/FFNetcode/Lobby/LobbyVisibility.cs": ("M", 9),
                 "Assets/Scripts/Diagnostics/FleetCullProbeSystem.cs": ("M", 9),
                 "Assets/Scripts/FFSystems/Multiplayer/RemotePlayerProjectionVisibilityAuditSystems.cs": ("M", 9),
                 "Assets/Tests/Presentation/HiddenFlyingStationTest.cs": ("M", 9),
                 "Assets/Scripts/FFSystems/Presentation/PlayerShipHideSystem.cs": ("D", 9),
                 "Assets/Scripts/FFSystems/Presentation/HoverFieldVfxPresentationSystem.cs": ("M", 9)}
        self.assertEqual(pe.hide_files(list(other), other), [])

    def test_the_note_asks_the_critic_what_is_still_drawn(self):
        self.assertTrue(any("still drawn where the hidden thing was" in q
                            for q in pe.census_questions("F7 hides the flying station: clips/f7.mp4")))
        self.assertEqual(pe.census_questions("Close-ups: z-fight: edge.png"), [])


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


class RealDeckTest(unittest.TestCase):
    """w770: a change a Steam Deck player meets says 'verified' on a real Deck or 'not verified on a real Deck'."""

    VERIFIED = ("Real Deck (Ben, 2026-10-09): verified, Steam client 1759 and SteamOS 3.7: Settings > Controls shows A/B/X/Y "
                "on the hotbar and the keybindings screen, and the game fills the whole screen after a fresh install")

    def fixture(self, name):
        body = (HERE / "fixtures" / f"{name}.md").read_text(encoding="utf-8")
        files = (HERE / "fixtures" / f"{name}.files").read_text(encoding="utf-8").splitlines()
        return body, files

    def deck_reasons(self, body, files=None):
        return [p for p in pe.check(body, files)[0] if "Real Deck" in p]

    def test_1249_the_w684_glyph_fix_had_only_a_deck_tour_and_now_fails_without_the_line(self):
        body, files = self.fixture("pr-1249-deck-glyphs")
        self.assertEqual(len(pe.check(body, files)[0]), 1)
        self.assertIn("Deck-facing change with no 'Real Deck:' line", "\n".join(pe.check(body, files)[0]))

    def test_1301_the_w767_resolution_fix_checked_on_a_linux_player_fails_without_the_line(self):
        body, files = self.fixture("pr-1301-deck-resolution")
        self.assertEqual(len(pe.check(body, files)[0]), 1)
        self.assertIn("Deck-facing change with no 'Real Deck:' line", "\n".join(pe.check(body, files)[0]))

    def test_a_changed_steam_file_alone_makes_it_deck_facing(self):
        body = edit(GOOD, "Kind: visual, simulation", "Kind: other")
        self.assertEqual(self.deck_reasons(body), [])
        self.assertTrue(self.deck_reasons(body, ["Assets/Scripts/Steam/ControllerPrompts.cs"]))
        self.assertTrue(self.deck_reasons(body, ["Assets/Scripts/Behaviours/Settings/DisplaySettingsController.cs"]))
        self.assertEqual(self.deck_reasons(body, ["Assets/Tests/SteamInput/DeckPromptFallbackTests.cs"]), [])

    def test_the_decks_name_in_the_evidence_makes_it_deck_facing(self):
        body = edit(GOOD, "Not verified: nothing", "Not verified: touch on the Steam Deck")
        self.assertTrue(self.deck_reasons(body))

    def test_not_verified_on_a_real_deck_passes_and_is_noted(self):
        body, files = self.fixture("pr-1301-deck-resolution")
        body = edit(body, "Kind: visual\n", "Kind: visual\n\nReal Deck: not verified on a real Deck: Proton's first frame and touch\n")
        problems, notes = pe.check(body, files)
        self.assertEqual(problems, [])
        self.assertIn("not verified on a real Deck: Proton's first frame and touch", notes)

    def test_verified_needs_who_both_versions_and_what_was_seen(self):
        body, files = self.fixture("pr-1301-deck-resolution")
        for line, fragment in (
                ("verified", "does not give the Deck's Steam client version"),
                ("verified (Ben): the Deck looked right; SteamOS 3.7", "Steam client version"),
                ("verified (Ben): Steam client 1759, SteamOS 3.7", "does not say what was looked at"),
                ("verified (Ben): the Deck tour at 1280x800, Steam client 1759, SteamOS 3.7, nothing clipped anywhere", "reads like the Deck tour"),
                ("mostly fine", "starts with 'verified' or 'not verified on a real Deck'")):
            reasons = "\n".join(self.deck_reasons(edit(body, "Kind: visual\n", f"Kind: visual\n\nReal Deck: {line}\n"), files))
            self.assertIn(fragment, reasons, line)

    def test_a_full_verified_line_passes(self):
        body, files = self.fixture("pr-1301-deck-resolution")
        self.assertEqual(pe.check(edit(body, "Kind: visual\n", f"Kind: visual\n\n{self.VERIFIED}\n"), files)[0], [])


class CloseUpTest(unittest.TestCase):
    """w1567: a claim that a visual defect is gone or that an effect happens names its close-up (checklists/visual.md
    5g). The failing case is w1470's PR #1921: "No z-fight with the Antimatter Nexus" and "the Guardian spaghettified",
    after which Ben saw both wrong."""

    CLOSEUPS = ("Close-ups: z-fight over terrain: edge-terrain-1x.png; z-fight over the Nexus ring: edge-nexus-1x.png; "
                "spaghettify: pull-strip-2.00-3.10s-every1f.png; stretch: hull-strip-2.00-3.10s-every1f.png; "
                "lensing: lens-1x.png; pulled in: pull-strip-1.00-2.00s-every2f.png\nSurfaces: terrain, the Nexus ring\n")

    def lance(self):
        body = (HERE / "fixtures" / "pr-1921-singularity-lance.md").read_text(encoding="utf-8")
        files, changes = pe.parse_files_file((HERE / "fixtures" / "pr-1921-singularity-lance.files").read_text(encoding="utf-8"))
        return body, files, changes

    def closeup(self, problems):
        return [p for p in problems if "close-up" in p.lower() or "Close-ups" in p or "Surfaces" in p]

    def test_the_lance_pr_claims_a_fixed_z_fight_and_a_spaghettify(self):
        claimed = pe.visual_claims(self.lance()[0])
        self.assertIn("z-fight", claimed)
        self.assertIn("spaghettify", claimed)

    def test_the_lance_pr_fails_for_its_missing_close_ups(self):
        body, files, changes = self.lance()
        found = self.closeup(pe.check(body, files, changes=changes)[0])
        self.assertEqual(len(found), 1, found)
        self.assertIn("no 'Close-ups:' line", found[0])

    def test_close_ups_for_every_claim_and_surface_pass(self):
        body, files, changes = self.lance()
        body = edit(body, "Looked: yes", self.CLOSEUPS + "Looked: yes")
        self.assertEqual(self.closeup(pe.check(body, files, changes=changes)[0]), [])

    def test_a_z_fight_checked_against_one_surface_only_fails(self):
        text = "No z-fight at the hole's edge.\nClose-ups: z-fight over the Nexus ring: edge-nexus-1x.png\n" \
               "Surfaces: terrain, the Nexus ring\n"
        problems, _ = pe.closeup_problems(text)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("terrain", problems[0])

    def test_a_z_fight_claim_needs_its_surfaces(self):
        problems, _ = pe.closeup_problems("The z-fight is gone.\nClose-ups: z-fight: edge-nexus-1x.png\n")
        self.assertTrue(any("no 'Surfaces:' line" in p for p in problems), problems)

    def test_a_clip_counts_only_slowed_and_placed(self):
        claim = "The sky lenses round the hole.\n"
        self.assertTrue(pe.closeup_problems(claim + "Close-ups: lensing: camp.mp4\n")[0])
        self.assertTrue(pe.closeup_problems(claim + "Close-ups: lensing: camp-0.25x.mp4\n")[0])
        self.assertEqual(pe.closeup_problems(claim + "Close-ups: lensing: camp-0.25x.mp4 2.0-3.1 s\n")[0], [])
        self.assertEqual(pe.closeup_problems(claim + "Close-ups: lensing: hole-1x.png\n")[0], [])

    def test_the_persons_words_and_pull_requests_are_not_claims(self):
        text = ('Intended look (Ben): "make them spaghettify ... no z fighting"\n'
                'Looked: yes, frames 10-40. "ships get pulled in" was his wish.\n'
                "This pull request into master ships the Lance.\n"
                "Looked for ghosts, leftovers, z-order and flicker: none\n")
        self.assertEqual(pe.visual_claims(text), {})

    def test_the_good_example_has_no_claim(self):
        self.assertEqual(self.closeup(pe.check(GOOD)[0]), [])

    def test_a_note_checks_its_files_and_writes_the_questions(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "edge-terrain-1x.png").write_bytes(b"x")
            note = folder / "note.md"
            note.write_text("The hole no longer z-fights.\nClose-ups: z-fight over terrain: edge-terrain-1x.png; "
                            "z-fight over the Nexus: edge-nexus-1x.png\nSurfaces: terrain, the Nexus\n", encoding="utf-8")
            questions = folder / "q.md"
            self.assertEqual(pe.main(["--note", str(note), "--questions", str(questions)]), 1)
            self.assertIn("is this true: The hole no longer z-fights.", questions.read_text(encoding="utf-8"))
            (folder / "edge-nexus-1x.png").write_bytes(b"x")
            self.assertEqual(pe.main(["--note", str(note)]), 0)


class TransitionStripTest(unittest.TestCase):
    """w1686: a transition ("stretches in", "swallowed", "seen as itself as it stretches") is shown every frame on the
    object, and a second opinion's "it disappears" is cleared only by that strip (checklists/visual.md 5h). The failing
    case is w1470's round 4 (PR #1921): a sheet every 0.2 s, the second opinion's "the Guardian disappears at once"
    explained away, and Ben, 2026-10-21: "it just kind of disappears"."""

    def round4(self):
        return (HERE / "fixtures" / "pr-1921-round4-swallow.md").read_text(encoding="utf-8")

    def test_round_4s_words_are_transition_claims(self):
        self.assertIn("transition", pe.visual_claims(self.round4()))
        for words in ("The Guardian stretches in about 4.0-5.6 s.", "A swallowed ship is seen as itself as it stretches.",
                      "Swallowed ships stay lit as themselves.", "One smooth animation from hull to strands.",
                      "The hull dissolves into the core."):
            self.assertIn("transition", pe.visual_claims(words), words)

    def test_round_4_fails_for_its_coarse_sheet_and_the_dismissed_flag(self):
        problems, questions = pe.closeup_problems(self.round4())
        self.assertTrue(any("is a transition" in p and "steps too coarsely" in p for p in problems), problems)
        self.assertTrue(any("the Guardian disappears at once" in p for p in problems), problems)
        self.assertTrue(any("every frame until its end state" in q for q in questions), questions)

    def test_round_4_fails_in_the_whole_pr_check(self):
        body = self.round4()
        self.assertTrue(any("is a transition" in p for p in pe.check(body, ["Assets/VFX/VfxSpaghettify.shader"])[0]))

    def test_an_every_frame_strip_with_its_seconds_passes(self):
        claim = "The Guardian stretches in about 4.0-5.6 s.\n"
        for entry in ("guardian-swallow-strip-3.40-6.20s-every1f.png", "guardian-strip-3.40-6.20s-every2f.png",
                      "guardian.png (3.4-6.2 s, every frame)"):
            self.assertEqual(pe.closeup_problems(claim + f"Close-ups: swallow: {entry}\n")[0], [], entry)

    def test_a_coarse_sheet_a_still_or_a_slowed_clip_alone_fails(self):
        claim = "Ships spaghettify into the core.\n"
        for entry in ("swallow-every-0.2s-3.4-6.2s.png", "sheet every 0.5 s 3.4-6.2 s.png", "hull-1x.png",
                      "pull-0.25x.mp4 2.0-3.1 s", "strip-3.4-6.2s-every6f.png", "strip-every1f.png"):
            self.assertTrue(pe.closeup_problems(claim + f"Close-ups: spaghettify: {entry}\n")[0], entry)

    def test_a_vanish_flag_beside_a_transition_needs_a_strip(self):
        flag = 'Second-opinion flags checked: "the Guardian disappears at once" is its hull going to the ghost.\n'
        claim = "The Guardian stretches in about 4.0-5.6 s.\n"
        strip = "Close-ups: swallow: guardian-strip-3.90-5.60s-every1f.png\n"
        self.assertTrue(any("disappears at once" in p for p in pe.closeup_problems(claim + flag)[0]))
        self.assertEqual(pe.closeup_problems(claim + flag + strip)[0], [])

    def test_a_flagged_snap_with_no_transition_claim_is_left_alone(self):
        # Merged PRs #2090 and #1994 (w1627, w1565): a teleport's SNAP explained, and a file named snap-rowA-*.json.
        for text in ("Jump's POP/SNAP flags are the teleport, at the same frame and strength in both arms.\n",
                     "Row B: `markedForRemoval` true on both | /srv/fff/review/w1565/snap-rowA-*.json\n"):
            self.assertEqual(pe.closeup_problems(text)[0], [], text)
        self.assertEqual(pe.vanish_flags("Row B | /srv/fff/review/w1565/snap-rowA-*.json, watch_video said so\n"), [])

    def test_the_persons_vanish_words_are_not_a_flag(self):
        text = ('Intended look (Ben): "it just kind of disappears ... one smoth animation"\n'
                "Looked for ghosts and pops: none\n")
        self.assertEqual(pe.vanish_flags(text), [])
        self.assertEqual(pe.closeup_problems(text)[0], [])


def _media_tools():
    import shutil
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return False
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(_media_tools(), "needs ffmpeg, ffprobe, numpy and Pillow")
class TransitionStripToolTest(unittest.TestCase):
    """w1686: transition_strip.py marks a model that vanishes in one frame, and not one that shrinks away smoothly."""

    def clip(self, folder: Path, vanish: bool) -> Path:
        import subprocess
        from PIL import Image, ImageDraw
        for i in range(120):                       # 2 s at 60 fps: a lit hull that shrinks over 1.0-1.8 s, or pops at 1.2 s
            im = Image.new("RGB", (320, 240), (10, 10, 30))
            if vanish:
                size = 80 if i < 72 else 0
            else:
                size = 80 if i < 60 else max(0, int(80 * (1 - (i - 60) / 48)))
            if size:
                ImageDraw.Draw(im).rectangle((160 - size, 120 - size // 3, 160 + size, 120 + size // 3), fill=(200, 60, 200))
            im.save(folder / f"f{i:03d}.png")
        out = folder / ("pop.mp4" if vanish else "smooth.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "60", "-i", str(folder / "f%03d.png"),
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "12", str(out)], check=True)
        return out

    def run_tool(self, clip: Path, folder: Path) -> dict:
        import json
        import transition_strip as ts
        self.assertEqual(ts.main([str(clip), "--from", "0.9", "--to", "1.9", "--claim", "hull", "--out", str(folder)]), 0)
        png = folder / "hull-strip-0.90-1.90s-every1f.png"
        self.assertTrue(png.exists())
        self.assertTrue(pe.is_strip(f"hull: {png.name}"))
        return json.loads(png.with_suffix(".json").read_text(encoding="utf-8"))

    def test_a_one_frame_vanish_is_marked(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self.run_tool(self.clip(Path(tmp), vanish=True), Path(tmp))
            self.assertEqual([p["frame"] for p in report["pops"]], [72], report["pops"])

    def test_a_smooth_shrink_is_not(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self.run_tool(self.clip(Path(tmp), vanish=False), Path(tmp))
            self.assertEqual(report["pops"], [])
            self.assertGreaterEqual(report["frames"], 59)


@unittest.skipUnless(_media_tools(), "needs ffmpeg, ffprobe, numpy and Pillow")
class TransitionJumpAndPaletteTest(unittest.TestCase):
    """w1816: transition_strip.py tracks the object and marks a one-frame jump in its place and a turn to colours that
    are not its own. w1685, after a clip passed with "no vanish, pop, swap or jump", Ben: "i dont like that it suddenly
    jumps to the center of the black hole and then also becomes that purple"."""

    def clip(self, folder: Path, kind: str, double: bool = False) -> Path:
        """A grey hull with an orange stripe spiralling into a hole with a purple disk, 2.5 s at 60 fps: smooth, with a
        jump most of the way in at frame 70, creeping then lunging in from frame 80, or turning purple over frames
        60-66. `double` writes each frame twice, as a half-speed capture does (w1685's half-speed take)."""
        import math
        import subprocess
        from PIL import Image, ImageDraw
        for i in range(150):
            im = Image.new("RGB", (480, 360), (8, 8, 20))
            d = ImageDraw.Draw(im)
            for k in range(40):
                d.point(((k * 97) % 480, (k * 53) % 360), fill=(150, 150, 170))
            glow = 1.0 + 0.08 * math.sin(i * 0.2)
            d.ellipse((188, 128, 292, 232), outline=tuple(int(c * glow) for c in (120, 60, 160)), width=12)
            d.ellipse((210, 150, 270, 210), fill=(0, 0, 0))
            u = min(1.0, max(0.0, (i - 30) / 108))
            if kind == "lunge":
                u = max(0.0, (i - 30) / 300) if i < 80 else min(1.0, 50 / 300 + (i - 80) / 40)
            if kind == "jump" and i >= 70:
                u = min(1.0, u + 0.45)
            if u < 1.0:
                r, a, s = 170 * (1 - u) ** 1.3 + 8, 0.3 + 5.0 * u, 1 - 0.8 * u
                x, y = 240 + r * math.cos(a), 180 + r * math.sin(a)
                hull, stripe = (150, 160, 175), (230, 140, 40)
                if kind == "purple" and i >= 60:
                    t = min(1.0, (i - 60) / 6)
                    hull = tuple(int(c + (p - c) * t) for c, p in zip(hull, (150, 60, 220)))
                    stripe = tuple(int(c + (p - c) * t) for c, p in zip(stripe, (170, 70, 230)))
                d.rectangle((x - 28 * s, y - 9 * s, x + 28 * s, y + 9 * s), fill=hull)
                d.rectangle((x - 28 * s, y - 2 * s, x + 28 * s, y + 2 * s), fill=stripe)
            for k in ((2 * i, 2 * i + 1) if double else (i,)):
                im.save(folder / f"f{k:03d}.png")
        out = folder / f"{kind}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "60", "-i", str(folder / "f%03d.png"),
                        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "12", str(out)], check=True)
        return out

    def run_tool(self, kind: str, *extra: str, double: bool = False) -> dict:
        import json
        import tempfile
        import transition_strip as ts
        a, b = (0.8, 4.8) if double else (0.4, 2.4)
        with tempfile.TemporaryDirectory() as tmp:
            clip = self.clip(Path(tmp), kind, double)
            self.assertEqual(ts.main([str(clip), "--from", str(a), "--to", str(b), "--claim", kind, "--track",
                                      "410,232", "--out", tmp, *extra]), 0)
            return json.loads((Path(tmp) / f"{kind}-strip-{a:.2f}-{b:.2f}s-every1f.json").read_text(encoding="utf-8"))

    def test_a_smooth_spiral_is_not_marked(self):
        report = self.run_tool("smooth")
        self.assertEqual((report["pops"], report["jumps"], report["surges"], report["off_palette"]), ([], [], [], []))
        self.assertGreater(sum(1 for t in report["track"] if t), 100)

    def test_a_creep_then_lunge_is_marked_where_it_speeds_up(self):
        report = self.run_tool("lunge")
        self.assertEqual(len(report["surges"]), 1, report["surges"])
        self.assertTrue(80 <= report["surges"][0]["frame"] <= 90, report["surges"])
        self.assertGreater(report["surges"][0]["times_before"], 3)

    def test_a_half_speed_capture_is_not_full_of_pops(self):
        """Every frame twice: before w1816 every real step was over 4x the median (half the steps are 0), so w1685's
        half-speed take showed 14 pops."""
        report = self.run_tool("smooth", double=True)
        self.assertEqual((report["pops"], report["jumps"], report["surges"]), ([], [], []))
        self.assertGreater(report["thresholds"]["repeat_frames"], 100)

    def test_a_jump_to_the_centre_is_marked_at_its_frame(self):
        report = self.run_tool("jump")
        self.assertEqual([j["frame"] for j in report["jumps"]], [70], report["jumps"])
        self.assertGreater(report["jumps"][0]["times_speed"], 10)
        self.assertEqual(report["off_palette"], [])

    def test_a_turn_to_purple_is_marked_from_its_first_frame(self):
        report = self.run_tool("purple")
        self.assertEqual(report["jumps"], [])
        self.assertEqual(len(report["off_palette"]), 1, report["off_palette"])
        span = report["off_palette"][0]
        self.assertEqual(span["hue"], "purple")
        self.assertTrue(60 <= span["from"] <= 64, span)
        self.assertGreater(span["to"], 100)

    def test_allowed_colours_are_not_foreign(self):
        report = self.run_tool("purple", "--allow-hues", "purple,magenta,blue")
        self.assertEqual(report["off_palette"], [])
