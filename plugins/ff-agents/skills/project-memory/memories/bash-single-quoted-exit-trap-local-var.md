---
name: bash-single-quoted-exit-trap-local-var
description: trap 'rm -rf "$tmp"' EXIT on a function-local $tmp under set -u exits 1 "tmp: unbound variable" at script end; expand it at definition
---

# A single-quoted EXIT trap on a local variable (w734, fff-ops-priv)

**Rule.** `local tmp; trap 'rm -rf "$tmp"' EXIT` in a function: the trap runs when the script ends,
after the function returned, so `$tmp` is unset and `set -u` fails the whole script (exit 1,
`line 1: tmp: unbound variable`) even though the work succeeded. Write
`trap "rm -rf -- '$tmp'" EXIT` with `# shellcheck disable=SC2064`.

**Why.** `fffctl credential issue` stored the credential, then exited 1 (ff-factory PR #237).

**How to apply.** Test the exit code of the whole script, not only its output; a stubbed
dependency (`FFFCTL=… bash script`) reproduces it without root.
