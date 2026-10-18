---
name: count-claude-tokens-from-a-worker
description: How a worker with no Anthropic API key counts text in Claude's own tokens (claude -p usage minus a baseline, with a text prefix so a leading "/" is not read as a slash command), and how to read a subagent's token usage from its transcript.
metadata:
  type: reference
---

**Counting text in Claude tokens without an API key (w1295, 2026-10-17, m5).** Workers have no `ANTHROPIC_API_KEY`, and `tiktoken` is
an OpenAI tokenizer (Claude counted about 1.5× its o200k count on C++ and Rust). The worker's own Claude login gives the
real count:

1. Prefix the text with a fixed line (`Text:\n`), feed it on stdin to
   `env -u CLAUDECODE -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_MESSAGING_SOCKET -u CLAUDE_CODE_MESSAGING_TOKEN claude -p --model sonnet --output-format json --system-prompt "Reply with the single word ok." --tools "" --max-turns 1`.
2. Add up `usage.input_tokens + cache_creation_input_tokens + cache_read_input_tokens`.
3. Subtract the same call fed only `Text:\n`. The baseline was the same on three calls in a row (79,746 tokens of fixed context here: user CLAUDE.md, plugins).

**The prefix is required.** A file that starts with `/` (a `//` or `/*` comment) is read as a slash command. k.cpp counted
127 tokens instead of 1,235, and a batch of Benchmarks Game sources counted 74,784 instead of 135,463. Nothing reported an
error. Each call carries the fixed context, so send a whole sample as one batch per language. A 750 KB batch (about 337k
tokens) went through in one call on Sonnet 5.5's 1M window. Use per-file calls only for a few small files.

**A subagent's tokens:** an Agent tool's background `output_file` is the subagent's JSONL transcript. Never read it into
context. Sum `message.usage` over the assistant lines with a script that prints only the totals, keeping the last line per
`message.id`. The notification's `subagent_tokens` is not the run's total: the 12 trial runs said about 47–54k each, while
their transcripts summed 173–290k input tokens (cache included) and 2–5k output tokens.

Scripts: the w1295 review folder (`w1295-tokens-2026-10-17.zip`: `claude_count.sh`, `trial/ref/usage.py`).
