---
name: read-a-player-minidump-at-the-fault
description: Reading a player's Windows minidump yourself with Python (minidump + capstone) — take registers from the exception stream's context, not the thread list; the dump holds no heap and ~256 bytes of code, so disassemble the release's own lib_burst_generated.dll; and test a "garbage" index against the version stamps on the same stack before calling it a bit flip (w2141).
metadata:
  type: project
---

Learned in w2141 (2026-10-25), checking FFBox's diagnosis of crash 20261025T115236Z-crash-64b5b84a70 (1.0.0.16,
`MarkChangedHierarchiesJob.Execute+0x35`, garbage chunk index from the query's chunk cache).

- **Tools**: `python -m pip install --user minidump capstone`. Never name your script `dis.py`: it shadows the
  stdlib `dis` module, and `import capstone` then runs your script and fails with a confusing traceback.
- **Registers at the fault come from the exception stream**, not `mf.threads`: the thread list holds each thread's
  context at dump time, and the faulting thread was by then inside Unity's crash handler (a syscall, small junk
  values). Read `mf.exception.exception_records[0].ThreadContext` (`DataSize`, `Rva`), seek to `Rva` in the file and
  unpack the AMD64 `CONTEXT`: Rax, Rcx, Rdx, Rbx, Rsp, Rbp, Rsi, Rdi, R8..R15, Rip as `<Q` from offset 0x78, 8 bytes
  apart (Rip at 0xF8). `ExceptionInformation[1]` is the address that faulted; check that it equals the
  effective address of the faulting instruction.
- **The dump has no heap and only ~256 bytes of code around RIP** (Unity's crash handler writes a small minidump), so
  you cannot read the container that held the bad value, and you cannot disassemble callers out of the dump. Fetch the
  release's own `lib_burst_generated.dll` (`fetch_ffbox_symbols {file: "lib_burst_generated.dll", version, platform:
  "WindowsPlayer", app: "main"}`), take its load base from the Player.log module list (`lib_burst_generated.dll
  (00007FFF...)`), and map a return address to a file offset through the PE section table. Then disassemble the caller
  with capstone and match its `[rbp+x]` slots to the stack words you read from the dump.
- **IJobChunk producer frame (Entities 1.4.7, Burst x64)**: `[rbp+0x98]` = the `UnsafeList<ChunkIndex>*` of the
  query's cached chunk list. Its `->Ptr` is re-read at the start of every batch, then `[Ptr + i*4]` gives the chunk
  index for batch i. `[rbp+0xc4]`/`[rbp+0xc8]` = batch begin/end. `[rbp+0]` = a copy of the query filter, whose first
  dword is `RequiredChangeVersion`, i.e. the system's `LastSystemVersion`.
- **Before you call a bad value a hardware bit flip, compare it with the version stamps on the same stack.** In w2141
  the bad chunk index `0x56d41ba5` was 7,039 below the system's `LastSystemVersion` `0x56d43724`. In that 8.5 h
  session GlobalSystemVersion rose about 48k per second, so 7,039 is about 0.15 s: the value is an Entities change
  version, not a small valid index with one bit flipped. That says the list's memory held another structure's data
  (freed and reused, or a wrong load from a failing CPU). It does not say which. Report it as that, not as "random
  garbage".

Related: [[symbolicate-a-release-crash-with-its-own-symbols]].
