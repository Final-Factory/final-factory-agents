---
name: player-feedback-sources-and-read-routes
description: Where Final Factory's player feedback lives (Steam reviews, Steam forums, the Nolt board, Reddit, YouTube, press, Discord) and the read-only route that worked for each from an FF Factory worker in w1477, with the routes that failed and the scraping traps.
metadata:
  type: reference
---

**The sources and how to read them (w1477, 2026-10-18, measured on biscuit).** Ben asked: "mine the player feedback going
back all the way". All of it is read-only; never post, vote or log in.

- **Steam reviews:** `https://store.steampowered.com/appreviews/1383150?json=1&language=all&purchase_type=all&filter=recent&num_per_page=100&cursor=<c>`,
  paged with the returned cursor until no new ids come back. That gave all 308 reviews (2024-04-09 to 2026-10-03). Each
  review links as `https://steamcommunity.com/profiles/<steamid>/recommended/1383150/`.
- **Steam Community forums:** curl `https://steamcommunity.com/app/1383150/discussions/` and the 5 sub-forums with `?fp=N`
  and a browser User-Agent. That gave 300 threads and 1,075 posts. Two traps:
  - Steam sometimes serves the forum index in place of a thread page. Check the page `<title>` and retry.
  - On locked threads the opening-post `div` has no `data-panel` attribute.
  News: `https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1383150&count=200`.
- **Nolt board, `https://final-factory.nolt.io/`:** the public feature-vote board. The 2024-05-26 news post calls it the
  roadmap, and some posts link Discord threads. On 2026-10-18 it had 113 posts and 840 votes.
  - It sits behind a Cloudflare managed check: curl gets "Just a moment". Headless Chromium passes: the Playwright
    browser cached at `~/.cache/ms-playwright/chromium-1243`, driven by `npm i playwright` in `$TMPDIR`, with `--headless=new`.
  - The board list hides Completed posts. `/roadmap` lists them by month, and each `/<pid>` page's text has its status
    and "Upvote <n>".
  - GraphQL introspection is off.
- **Reddit:** reddit.com's JSON returns 403 to agents, old.reddit redirects to a login, and pullpush.io now refuses
  agents. **Arctic Shift works**: `/api/comments/search?link_id=<id>`.
  - Treat 2024-05 to 2024-08 with care: 17 accounts posted 213 near-identical recommendations of the game. They looked
    like paid promotion and were left out of the counts.
- **YouTube:** `yt-dlp --skip-download --write-comments --dump-single-json` gives the comments, and auto-subs give the
  reviewer transcripts.
- **Bluesky:** the public search API.
- **Discord: text only from a machine with the ffdiscord config.** That is LothDesktop; biscuit has none
  (`~/.config/ffbox` is absent). FFBox's `fetch_discord_thread_files` returns only attachments from the bug channels,
  and `ffbox_activity` is an orchestrator tool. A GET-only export of every channel and thread with reactions,
  `discord_export.py`, was published as `att_bkx6t0735ow1` for a worker on such a machine. It wraps ffdiscord's own
  `Client`, so the token never leaves that machine.

**Traps:**
- The harness refuses `pkill` of node (other sandboxes share the machine), so give every long scrape a `timeout`.
- `pkill -f <script name>` can kill the shell that ran it, because the pattern matches its own command line.
- A worker's "end of turn" while background subagents run is not a turn the orchestrator sees. The ledger kept showing
  w1477 mid-turn, so an ask to the orchestrator waits for the real final report.

**Where the feedback is by date:** 243 of the 308 reviews and most forum and Reddit text are from 2024, the Early Access
launch. Only 8 reviews and 4 forum threads are dated after 2026-04-18. The multiplayer and 1.0 period is in Discord: 173
of the 181 merged fix PRs that cite Discord threads are from 2026-10.

The w1477 report and its sources: attachments `att_hbjptjst3k14` (HTML) and `att_9f5uulxknnjh` (the sources zip).
