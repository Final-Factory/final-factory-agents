# Public copy: before it reaches the person or the public

For anything strangers read in our name: website pages, Steam store text, Discord and Reddit
posts, emails, press kits, patch-note intros, and text a person will paste. Why: [public copy
sounds like the person](../lessons/public-copy-sounds-like-the-person.md) (w1825, w1926).

**The line:** Cut any line that doesn't need to exist. Write the way the person talks: short,
plain, casual. No taglines or marketing words, no run of sentences or paragraphs all the same
length, and no lines explaining what the page is. Then a fresh critic reads only the copy and quotes every line that
sounds machine-written. A clean word lint isn't a pass.

0. **A bug thread: were you asked?** (w2711, lothsahn: "Stop") Before a `post_as_max` into a #bug-reports,
   dev_bug_reports or feedback thread, quote the message in that thread that mentions Max, or the person's words asking
   for this post. Neither, and above all a question to the player you thought of yourself (a save, a repro step): do not
   post; put it in your report as a blocker, and the person's orchestrator decides.
1. **Cut first.** Read each line and ask who'd miss it. A line that tells readers what the page
   is, how it's sorted or where else to look ("newest first", "Older updates are in Steam news")
   goes, unless a reader would really get lost without it. Then it's one short clause, not a
   sentence of its own.
2. **The person's voice.** First person where they'd use it. Use the
   words they use about their own game, not a pitch. No taglines, slogans, "whether you're",
   "embark", "immersive", "unlock the secrets". The `plain-writing` skill has the full list of
   habits; for Ben, ff-marketing `brand/voice.md`.
3. **Uneven rhythm.** Three sentences of about the same length in a row, or paragraphs that all land within a few words of each other (w1825: 34 to
   36), read as a template. Shorten one, or merge two.
4. **Run the flagger:** `python "$FF_SKILLS/evidence-gate/copy_check.py" <file>...` (.md, .txt or .html, or `-` for stdin).
   Fix each flag or have a reason for keeping it. It misses things, so step 5 still runs.
5. **A fresh critic.** Start a new subagent (Claude Code: `general-purpose`; Codex: a new
   default agent) and give it only the copy, no brief and no draft history, with: "You are a
   reader who hates machine-written prose. Quote every line of this copy that sounds like an AI or
   a marketer wrote it, and say in a few words why. Also quote any line a reader wouldn't miss.
   If nothing qualifies, say so." Rewrite or cut every quoted line, then send the new copy to
   another fresh critic. Stop once a critic quotes nothing.
6. **Show it and wait.** The person sees the final copy as plain text, plus one line saying the
   critic quoted nothing. Publish only after they OK it.
