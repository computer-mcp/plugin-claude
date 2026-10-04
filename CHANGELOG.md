# Changelog

All notable user-visible changes to the Claude Code plugin are documented here.

## Unreleased

## 0.1.1 — 2026-09-29

- Add `claude.run.release`, which frees a retained result only after its cleanup
  is confirmed. Cancellation and retained results keep execution ownership.
- Expose owned runs through the standard MCP work resource, so a compatible host
  can account for work after a tool reply and across live configuration changes.
- Bound stream parsing and event retention while keeping native session identity
  and final results explicit.

## 0.1.0 — 2026-09-24

- First release: a canonical CLI tree for the headless Claude Code surface, a
  stdio MCP adapter with six tools for print and stream-json runs, background
  runs, events, results, session continuation and cancellation, and usage Skills.
- Requires Computer MCP 1.2.2 or later on Apple Silicon, Python 3.13 or newer,
  and Claude Code 2.1.59.
