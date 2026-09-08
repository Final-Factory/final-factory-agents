---
name: tool-session-polling-and-archive-verification
description: Long commands must expose and poll their terminal session; empty outer-cell output is not a process verdict, and archive evidence compares independently generated raw tar hashes
metadata:
  type: project
---

For a long command issued through `functions.exec`, forward the nested terminal result with
`text(await tools.exec_command({ ..., yield_time_ms: 1000 }))`. Keep the returned
`session_id` and forward polling results too, with
`text(await tools.write_stdin({ session_id: id, chars: "", yield_time_ms: 1000 }))`.
`functions.wait` resumes only the
outer JavaScript cell. Empty outer-cell output does not establish that the command exited, was
killed, or that the host is blocked. Inspect the real terminal exit status before diagnosing or
retrying; do not launch blind `nohup` retries.

For an archive streamed from another machine, preserve permissions and symlinks with an
uncompressed `tar -cpf -` stream. Independently regenerate the source-side raw-tar SHA and hash
the local `.tar` bytes (or `gzip -dc` for an existing gzip archive), using `pipefail` on every
pipeline. Matching hashes and matching full `tar -tf` inventories plus `tar -tvf` manifests
prove the copy without a second full network transfer. M3 archive session `6549` ran for several
minutes and exited 0 when polled; its independently regenerated source and local raw-tar hashes
matched. The earlier worker had lost the nested terminal results and incorrectly
reported a host termination limit.
