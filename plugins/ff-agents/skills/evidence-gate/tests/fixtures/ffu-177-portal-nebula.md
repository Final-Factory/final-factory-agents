Part of: w2895 (row R.T5: the Ancient Portal's nebula as original art)

Shortened from ffu #177 as it went to Ben (the ffu repo is private): its evidence measured closeness to FF1's texture
file and a critic verdict, with no capture of FF1's screen and no art-language line.

## Evidence
- **Not a copy:** generated from a procedure that reads no pack file; no SHA-256 match against the pack folders.
- **Close to FF1's texture** (full images, MEASURED): mean RGB 41/59/91 against 44/59/84; median luma 48.0 against 54.3.
- **Fresh critic (round 15): ACCEPT-WITH-NITS.** Its nits: the core is cream-white where it should be more orange.
- **Checks:** `cargo fmt --check`, `cargo clippy` and `cargo test -p ffu-bake` pass.
- Stills: the round-15 review folder.
