# plugin-claude Agent Guide

Read `README.md`, `computer-mcp-plugin.toml`, and `Documentation/Reference/Interface.md` before editing.

Keep vendor installation, authentication, subscription/API usage, updates, plugins, and setup tokens outside this repository. The external Claude Code executable is a dependency, not bundled code. Do not run authenticated model prompts merely to validate package structure.

`cli-tree.json` is publisher-owned static interface data for the pinned Claude Code baseline. Update it only after verifying the real native `--help` and `--version`. Keep coverage explicitly partial.

`bin/claude-mcp-adapter` owns only bounded CLI stream-json to MCP translation. It must use the host-selected current working directory, bound input/output, terminate owned child processes, and never elevate Claude Code permissions implicitly. `dontAsk` remains the default; bypass permission modes are not exposed.

Use Python standard library only unless a dependency demonstrably removes required complexity. Tests must cover MCP initialization, tool discovery, stream-json parsing, permission-boundary rejection, cancellation, deterministic package contents, and executable archive mode.

Before handoff run unit tests, the native non-model interface check, deterministic package build, Computer MCP package validation/doctor where available, and git status. Do not publish or create a release implicitly.
