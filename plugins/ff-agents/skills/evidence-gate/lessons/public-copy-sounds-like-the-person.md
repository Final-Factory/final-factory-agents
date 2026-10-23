---
name: public-copy-sounds-like-the-person
description: "Public copy (site pages, Steam text, Discord and Reddit posts, emails, press kits, text to paste) reads like the person wrote it: cut any line nobody would miss, short and plain, uneven rhythm, no taglines, no lines about the page itself. A fresh critic reads it before anyone sees it; a clean word lint is not a pass. Text to paste goes in the chat as plain text."
date: 2026-10-23
---

# Public copy sounds like the person

**Rule.** Write public copy the way Ben talks, and cut any line nobody would miss. Then a fresh
critic reads only the copy and quotes each line that sounds machine-written, and you rewrite
until it quotes nothing. A word lint can't sign it off.

**Why.** Ben has said it twice.

On 2026-10-02 he sent back text he was meant to paste. Lines like "I make Final Factory" and
"build one space factory" were stiff, and he called the ad wording "kind of awkward".

On 2026-10-23 (w1825, the new final-factory.com) he had already asked to "make it not sound like
LLM prose". The worker ran a word lint and it came back clean. The Patch notes page went live
opening with:

> Every build since late September 2026, newest first. New builds reach Steam's opt-in betas
> first. Older updates are in Steam news.

Ben: "this text is LLM speak lol i told you not to use llm prose!"

It's three sentences of 8, 7 and 6 words, and every one of them explains the page to someone
who is already on it. The feature paragraphs on the same site were all 34 to 36 words long; the
worker noticed that and shipped them anyway.

**How to apply.** Before anyone sees the copy, run the [public copy
checklist](../checklists/public-copy.md):

- Run `copy_check.py` on the copy. It flags even rhythm, repeated openings, explainer lines,
  stock phrases and em dashes. It can miss things: Ben's 2026-10-02 lines pass it clean.
- Give the copy, and only the copy, to a fresh critic. Fix or cut whatever it quotes.
- Show Ben the copy and get his OK before it's sent or published.

## Text for the person to paste is plain (2026-10-02)

When a person is going to paste something (a Reddit post, an email, Steam text), put it in the
message as plain text, without code blocks or Markdown they'd have to strip out. Ben,
2026-10-02: "in general give me text that i need to paste that isnt code or whatever in non
formatted text". Code blocks copy with their own line breaks, and Markdown marks end up in the
post. Give one version, not three, unless they asked for options. Voice: ff-marketing `brand/voice.md` and the `plain-writing` skill.
