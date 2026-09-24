# Interface contract

## Native and host contracts

`cli-tree.json` is the canonical, explicitly partial command contract for the tested native Claude Code version. It maps print mode and declared options to exact argv with `--` before the prompt. New or changed upstream flags require a reviewed plugin update, not runtime parsing of human help.

The native version assertion runs before each adapter execution and each host-projected CLI call. Native command availability does not establish account authentication or backend access. The CLI contribution returns a single native JSON result. The MCP adapter independently consumes print-mode stream-json with verbose and partial-message output; it does not parse the terminal UI or use hosted Managed Agents.

The adapter implements newline-delimited MCP JSON-RPC initialization, tools/list, tools/call, ping and cancellation. Supported MCP dates are 2024-11-05, 2025-03-26 and 2025-06-18. Unsupported proposals receive a supported date, not an unimplemented echo. Tool schemas describe accepted arguments. Tool results use `structuredContent.result`; `isError` indicates a failed operation, distinct from a JSON-RPC protocol error.

## Tools

| Native MCP tool | Behavior |
| --- | --- |
| `claude.run` | Execute a bounded prompt and wait for the final native result and process cleanup |
| `claude.run.start` | Return an adapter-owned `run_id` without holding the caller until completion |
| `claude.run.list` | List retained runs owned by this adapter process |
| `claude.run.result` | Return current state or an explicitly completed final result |
| `claude.run.events` | Read a bounded cursor page of native stream-json events |
| `claude.run.cancel` | Cancel one adapter-owned run and wait through normal cleanup on subsequent result reads |

The host may prefix these names; discover actual projections with tools/list. The adapter retains at most 32 total runs, of which at most four can be active. Run handles and event pages are memory-owned, not a second vendor conversation database. Replacing the adapter invalidates these handles; it does not delete native saved conversations.

## Session and permission semantics

`resume_session_id`, `continue_previous` and a new `session_id` are mutually exclusive. New session IDs must be UUIDs. No-session-persistence cannot resume a saved conversation. An explicit native ID remains the native ID; it is not interchangeable with `run_id`. Resume starts another native print process using the selected conversation. Native persistence and its own writer-conflict rules remain authoritative.

The MCP default is `permission_mode: dontAsk`; callers can explicitly select `plan` or `acceptEdits`. CLI projection requires an explicit mode. These choices preserve native behavior rather than granting host permission. The adapter does not expose bypass modes or create implicit permission responses. Native user/project settings still apply. Interactive permission brokerage and the full Agent SDK callback API are not part of this headless stream interface.

Model, effort, appended system prompt and optional budget are forwarded only when supplied. No adapter-imposed model budget is silently added. Vendor credentials/environment remain user-owned. The plugin installs or logs in to nothing, and copied host metadata is never a credential.

## Streaming, completion and cancellation

Each native frame is bounded to 1 MiB before waiting for a newline. The event buffer retains at most 256 events/256 KiB; it reports overflow, omitted oversized events and stale cursors. Pages expose next_cursor, has_more and missed_events, never an unbounded whole history. The final native event is retained separately with a 128 KiB bound; oversized final data fails rather than masquerading as successful truncated output.

Success requires exactly one valid native result event, a non-error native outcome, a successful process exit, and confirmed process cleanup. A final event followed by a hung process still times out. Missing/duplicate/malformed final events, a nonzero exit, cancellation, timeout or cleanup uncertainty are tool errors. Native errors and the final event remain available in the bounded result. `completed: true` means this adapter run settled, not that its task succeeded; inspect `is_error` and state.

The default execution timeout is 600 seconds, with a configurable maximum of 1800 seconds. Process setup/cleanup can add bounded latency. Synchronous MCP cancellation targets the corresponding run. For detached runs use run.cancel with the returned run_id. Cancellation kills only the owned vendor process group; it does not erase a persisted conversation or retry the prompt.

A private supervisor observes parent/connection shutdown, pins the native group leader until termination/reaping, and reports cleanup over a separate bounded channel. EOF without acknowledgement is cleanup_unconfirmed. This is owned process-group cleanup, not a sandbox preventing deliberately escaped descendants. Host private descriptors and reserved COMPUTER_MCP environment metadata are excluded from the native process. Native tools and configuration can still act beyond the initial working directory.

## Sources

- https://code.claude.com/docs/en/cli-reference
- https://code.claude.com/docs/en/headless
- The installed native `claude --version` and `claude --help` used to maintain the pinned CLI tree.

Fixture protocol checks, native interface checks, exact-host interoperability and authenticated model execution are recorded separately.
