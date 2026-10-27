---
name: rawreader-digests-run-one-at-a-time-and-raws-publish-as-zip-parts
description: Batch digests (MainThreadTree, SyncPoints, CpuBudget) that share one rawreader project must run one after another, or the second Unity exits 137 and writes nothing. A profiler .raw is over publish_review's 200 MB limit and must go up as deflate .zip parts.
metadata:
  type: project
---

**Run rawreader digests one at a time (w2339, 2026-10-27, beast).** Two `unity-slot run -- Unity.exe -batchmode
-projectPath <one rawreader project> -executeMethod MainThreadTree.Batch ...` calls ran side by side: one on the
idle and flying .raws, one on the zoom .raws. Every zoom run's log ends with "Exiting without the bug reporter.
Application will terminate with return code 137", and no `-mtOut` or `-spOut` file was written. Unity allows one
editor per project. A wrapper that echoed `$?` after `unity-slot run` still printed "exit 0", so it hid the failure.
How to apply it:
- Put every digest in one serial script.
- After each run, check that the output file exists (`ls "$B.tree.txt"`). The exit status does not prove it.
- To digest in parallel, give each run its own reader project (`-createProject`, then copy
  `scripts/bench/rawreader/*.cs` into it, as in `capture_raw.sh`).

**A .raw goes up as zip parts.** `publish_review` takes at most 200 MB per file and 500 MB per call. It accepts
images, video, .md/.txt/.json and .zip only, so a `.csv` is refused (rename it to `.txt`). Measured on
JustPlay1003 development-player captures:
- A 518 MB zoom .raw came to 99 MB as a deflate zip (level 6, 5.2 times smaller).
- A 2.6 GB 60 s `-ffBenchProfile 1` .raw came to about 575 MB, which is too big for one file.

Split it into 600 MB byte ranges, each written as its own zip (`zipfile.writestr("<name>.raw.partN", chunk)`). That
gave five parts of at most 117 MB, published four per call. Say in the note how to rebuild it: unzip every part,
then `cat <name>.raw.part1 ... partN > <name>.raw`. Publish the text digests beside the parts, because a reviewer
reads those first.

**A new reader project needs `Assets/csc.rsp` with `-unsafe`** (w2392, 2026-10-27, beast). `StructuralChangeDigest.cs`
uses unsafe code. In a project made with `-createProject` it fails with `error CS0227`, and every `-executeMethod`
run aborts with "Scripts have compiler errors" and writes no output. Write `echo "-unsafe" > <project>/Assets/csc.rsp`
when you copy the `.cs` files in.

**`unity-bridge.py` can name a stale port** (w2392). Its status file in `~/.unity-mcp` said 6400, and the connection
was refused, while the `mcp__UnityMCP__*` tools reached the same editor. When that happens, use the MCP tools.
