# Interface contract

## Native and host contracts

`cli-tree.json` is the canonical, explicitly partial command contract for the tested native Claude Code version. It maps print mode and declared options to exact argv with `--` before the prompt. New or changed upstream flags require a reviewed plugin update, not runtime parsing of human help.

The native version assertion runs before each adapter execution and each host-projected CLI call. Native command availability does not establish account authentication or backend access. The CLI contribution returns a single native JSON result. The MCP adapter independently consumes print-mode stream-json with verbose and partial-message output; it does not parse the terminal UI or use hosted Managed Agents.

The adapter implements newline-delimited MCP JSON-RPC initialization, tools/list, tools/call, resources/list, resources/read, ping and cancellation. Supported MCP dates are 2024-11-05, 2025-03-26 and 2025-06-18. Unsupported proposals receive a supported date, not an unimplemented echo. Tool schemas describe accepted arguments. Tool results use `structuredContent.result`; `isError` indicates a failed operation, distinct from a JSON-RPC protocol error.

## Host risk metadata

Every MCP tool declares `_meta["io.github.computer-mcp/risk"]`. Model execution
and continuation declare `full-shell`: native permission defaults are not a
host-enforced sandbox. Catalog, result, event and pending-request inspection
declare `read-only`. Cancellation and owned-process retirement declare
`destructive`. The host applies these as minimum classifications, intersects
its own grants, and retains approval authority. Standard MCP annotations remain
hints rather than permissions.

## Tools

| Native MCP tool | Behavior |
| --- | --- |
| `claude.run` | Execute a bounded prompt and wait for the final native result and process cleanup |
| `claude.run.start` | Return an adapter-owned `run_id` without holding the caller until completion |
| `claude.run.list` | List retained runs owned by this adapter process |
| `claude.run.result` | Return current state or an explicitly completed final result |
| `claude.run.events` | Read a bounded cursor page of native stream-json events |
| `claude.run.cancel` | Cancel one adapter-owned run and wait through normal cleanup on subsequent result reads |
| `claude.run.release` | Discard one completed result and its events after process and worker cleanup are confirmed |

The host may prefix these names; discover actual projections with tools/list.
The adapter retains at most 32 total runs, of which at most four can have active
or unconfirmed cleanup. Starting a new run at capacity evicts the oldest completed
result whose process and worker cleanup are confirmed. Explicit `run.release`
discards the same retained result sooner. Active work returns `run_active`;
uncertain cleanup returns `cleanup_unconfirmed` and remains retained. Reading
results/events and requesting cancellation do not release the handle.

Run handles and event pages are memory-owned, not a second vendor conversation
database. Replacing the adapter invalidates these handles; it does not delete
native saved conversations. Explicit release also leaves native persistence
unchanged. Save the native session ID before releasing a result if it is needed
for a later resume.

## Ordinary MCP work resource

Every tool declares `_meta["io.github.computer-mcp/work"]` with `format_version: 1`
and URI `computer-mcp://runtime/work/v1`. The same URI is available through
`resources/list` and `resources/read`; it follows the host's
[provider-work contract](https://github.com/computer-mcp/computer-mcp/blob/master/Documentation/Reference/MCPProtocol.md#downstream-provider-work).
It does not require private Host Services, change native permissions, or itself
enable host configuration changes.

A host supplies `_meta["io.github.computer-mcp/work-invocation"]` as a UUID on
each tool call. Each newly reserved run retains its creation call's UUID.
Arguments cannot supply this identity. Subsequent result, event, cancel and
release calls do not rebind the original acquisition. Ordinary clients may
omit the metadata and still use every tool. While an unbound handle is retained,
work observation returns an error because it cannot prove a complete host-bound
snapshot.

The resource returns a complete bounded snapshot with one instance UUID and a
monotonic revision, containing `kind: claude.run`, the adapter `run_id`,
`acquired_by`, and `state`. Pending version checks, process startup, streaming
execution and retained completed results are `active` owners. A cleanup failure
is `uncertain`, even when `completed` is true. Confirmed completion alone does
not remove retained result access: release or bounded capacity eviction ends
the handle's ownership. Snapshot errors preserve the last valid revision.
The declaration is connection-local; gateway reexports omit it from their wire
tool metadata.

## Session and permission semantics

`resume_session_id`, `continue_previous` and a new `session_id` are mutually exclusive. New session IDs must be UUIDs. No-session-persistence cannot resume a saved conversation. An explicit native ID remains the native ID; it is not interchangeable with `run_id`. Resume starts another native print process using the selected conversation. Native persistence and its own writer-conflict rules remain authoritative.

The MCP default is `permission_mode: dontAsk`; callers can explicitly select `plan` or `acceptEdits`. CLI projection requires an explicit mode. These choices preserve native behavior rather than granting host permission. The adapter does not expose bypass modes or create implicit permission responses. Native user/project settings still apply. Interactive permission brokerage and the full Agent SDK callback API are not part of this headless stream interface.

Model, effort, appended system prompt and optional budget are forwarded only when supplied. No adapter-imposed model budget is silently added. Vendor credentials/environment remain user-owned. The plugin installs or logs in to nothing, and copied host metadata is never a credential.

## Streaming, completion and cancellation

Each native frame is bounded to 1 MiB before waiting for a newline. The event buffer retains at most 256 events/256 KiB; it reports overflow, omitted oversized events and stale cursors. Pages expose next_cursor, has_more and missed_events, never an unbounded whole history. The final native event is retained separately with a 128 KiB bound; oversized final data fails rather than masquerading as successful truncated output.

Success requires exactly one valid native result event, a non-error native outcome, a successful process exit, and confirmed process cleanup. A final event followed by a hung process still times out. Missing/duplicate/malformed final events, a nonzero exit, cancellation, timeout or cleanup uncertainty are tool errors. Native errors and the first valid final event remain available in the bounded result, including after later malformed output, timeout, cancellation or cleanup failure. `cleanup_error` records cleanup failure separately from an earlier execution `error`; `cleanup_confirmed` reports the process cleanup outcome. Successful final events require a `success` subtype, native session identity and textual result; unknown extension fields are retained. `completed: true` means this adapter run settled, not that its task succeeded; inspect `is_error` and state.

The default execution timeout is 600 seconds, with a configurable maximum of 1800 seconds. Process setup/cleanup can add bounded latency. Synchronous MCP cancellation targets the corresponding run. For detached runs use run.cancel with the returned run_id. Cancellation kills only the owned vendor process group; it does not erase a persisted conversation or retry the prompt.

A private supervisor observes parent/connection shutdown, pins the native group leader until termination/reaping, and reports cleanup over a separate bounded channel. EOF without acknowledgement is cleanup_unconfirmed. This is owned process-group cleanup, not a sandbox preventing deliberately escaped descendants. Host private descriptors and reserved COMPUTER_MCP environment metadata are excluded from the native process. Native tools and configuration can still act beyond the initial working directory.

## Sources

- https://code.claude.com/docs/en/cli-reference
- https://code.claude.com/docs/en/headless
- The installed native `claude --version` and `claude --help` used to maintain the pinned CLI tree.

Fixture protocol checks, native interface checks, exact-host interoperability and authenticated model execution are recorded separately.

## Continuation binding

Tools that accept an existing adapter handle declare
`_meta["io.github.computer-mcp/continuation"]` with format version 1. The selector
matches kind `claude.run` and primary resource `id` against argument
`run_id` using JSON Pointer `/run_id`. This identifies the actual
connection-owned lifetime; it does not rebind acquisition or grant permissions.
New work and unscoped listings do not claim an existing owner. The declaration
uses ordinary MCP metadata and requires no private Host Services. Hosts validate
and retain it on its originating connection; gateway reexports strip it. Runtime
generation selection remains host-owned, and this declaration alone does not
enable live configuration changes.
