---
name: review-media-goes-inline
description: "Every still and clip a person must look at goes into the message as its own ![name](<absolute path>) line, which FF Factory's page shows as an image or a video player: never a bare path, a folder, a wildcard or a file name with no folder. A folder is each of its clips and stills, newest first, never its .preview/ encodes. Before you send anything a person reads, scan it for review paths, folders and media names not in ![..](<..>) form. w1384 (Ben, 2026-10-13 and 2026-10-15)."
date: 2026-10-15
---

# Review media goes inline, never as a bare path

**The rule.** When a person has to look at a still or a clip (a look to OK, a before/after, a preview video), each file
goes into the message they read as its own `![name](<absolute path>)` line. FF Factory's page shows a PNG, JPG, GIF or WebP
inline and an MP4, WebM or MOV as a player (`/api/image`; review files are under the review folder, `/srv/fff/review/<topic>/`
on the portal). That holds for a worker's report, an orchestrator's relay, a `[needs you]` answer, a PR description the
person reads in chat, and a dispatcher question.

- **A folder is its files.** `/srv/fff/review/w1182-fog-look-v4/` is one `![..](<..>)` line per clip and still in it,
  newest version first, never the `.preview/` encodes beside them.
- **A bare name is a path.** `clip.mp4` or `![clip](<clip.mp4>)` is its absolute path under the review folder.
- **A wildcard is its matches**, each its own line.
- **Never a path in backticks or plain text as the way to see it.** A path may appear as well (to find the file), but
  only beside the inline line.

**Why** (w1384). Ben, 2026-10-13 (w1058 and w1061, preview 2): "you have to inline preview videos in this chat for me
to verify them". Ben, 2026-10-15, after his orchestrator relayed a `[needs you]` question for w1182 whose only pointer was
`/srv/fff/review/w1182-fog-look-v4/`: "I need to see the preview video for the fog. Stop giving me paths to videos and
inline the videos like you should be doing and I've reminded you as such like 100 times".

The same miss happened twice in one day, two ways:

- w1182: the dispatcher's question named only the folder. w1378's `[needs you]` builder passed the folder through as
  code, and the orchestrator relayed it.
- w1241: the digest built its files from a kept report that FF Factory clips in the middle. `glow_800_closeup.jpg`
  became `glow_800_closeup.jp`.

The rule had been in the orchestrator's brief all along, and it did not hold. So FF Factory now resolves review paths on
its disk (`server/reviewMedia.ts`): folders become files, bare names become absolute paths, cut-off names become their
folder's files. It also puts inline what a person's orchestrator names bare (ff-factory PR for w1384, docs/orchestrators.md
"Review media inline"). That is a backstop: write it inline yourself.

**How to apply.**

- Writing a report: publish with `publish_review`. Its answer gives the absolute paths. Put each file in as `![what it
  shows](<path>)`, not the folder.
- Relaying (an orchestrator, the dispatcher): copy each `![..](<..>)` line from what you relay. If you were given a
  folder or a bare name, turn it into the file lines before you send. FF Factory's `[needs you]` already lists them that
  way.
- Before you send, run the check in [done.md](../checklists/done.md) item "Review media inline": any review path, folder,
  wildcard or `.mp4`/`.png`/`.jpg` name in the message that is not inside `![..](<..>)` is a miss.
