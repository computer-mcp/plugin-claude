---
description: Keep the Claude Code adapter's translation bounded and its permission defaults safe, and test its protocol paths.
---
# plugin-claude Agent Guide

## Task Route

- Read `docs/Reference/Interface.md` before editing.
- Before handoff, run the unit tests and the native non-model interface check.

## Adapter

- `bin/claude-mcp-adapter` owns only bounded CLI stream-json to MCP
  translation. It uses the host-selected working directory, bounds input and
  output, terminates the child processes it owns, and never elevates Claude
  Code permissions implicitly. `dontAsk` remains the default; bypass permission
  modes are not exposed.
- Use the Python standard library unless a dependency demonstrably removes
  required complexity. Tests cover MCP initialization, tool discovery,
  stream-json parsing, permission-boundary rejection, cancellation,
  deterministic package contents and executable archive mode.
