---
name: list-env-by-name-never-values
description: "To find out which environment variables a session has, list their names only (env | cut -d= -f1). Never print env lines and hide the values with a sed or grep you wrote: it hides only the names you thought of, and every other value lands in the transcript."
metadata:
  type: feedback
---

# List environment variables by name, never their values

**Rule.** When you need to know what the environment holds (which portal URL, which token is set, which vault
values the portal gave this run), print names only:

```sh
env | cut -d= -f1 | grep -i -E 'fff|portal|gh_'   # which names exist
printenv SOME_NAME | wc -c                         # that one is set, and how long, without its value
```

Read a value only by its exact name, and only when the value is not a secret (a URL, a port, a path). Never
`env | grep ... | sed 's/=.*TOKEN.*/=***/'` or any filter that redacts the values *you* thought of: a worker's
environment carries vault values under names you did not guess (passwords, keys, webhook URLs).

**Why.** w1664 (2026-10-21, beast/slot2): looking for the daemon's local interface, a worker ran `env | grep`
with a sed that hid only names containing TOKEN. The vault's `FFSTEAM_PASSWORD` value was printed into the
session's transcript. It went nowhere else (no file, commit or post), but a transcript is kept and read again,
and the person who owns the secret had to be told so they could decide about rotating it.

**How to apply.** Names first, always. If a value must be checked, compare it without printing it
(`[ "$X" = "$Y" ] && echo same`, `printenv X | sha256sum | cut -c1-8`). If a secret does reach your output,
say so at the top of your report, naming the variable and never repeating the value, so its owner can rotate it.
