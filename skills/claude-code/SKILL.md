---
name: claude-code
description: Use this Computer MCP plugin's verified Claude Code CLI and bounded MCP run, event, result, cancellation and native-session continuation tools.
---

# Claude Code

Discover actual host tool names/schemas and select an authorized workspace. Use the typed CLI print command when a final native JSON result is sufficient. It requires explicit permission_mode and uses a fixed verified native version.

For observable execution, use `claude.run.start`, retain run_id, page through `claude.run.events`, and inspect `claude.run.result`. Use `claude.run` only when waiting for the complete operation is appropriate. `claude.run.cancel` targets an exact run; inspect its subsequent result to confirm settlement. Cancelling the original start request after it returned does not cancel the detached run.

Adapter run_id and native session_id are different. Resume with an explicit native resume_session_id, continue_previous, or create a session_id; do not combine them. The adapter's in-memory handles are invalid after process replacement, but native persisted conversations remain under vendor control. Unknown execution outcome does not authorize replaying a prompt.

permission_mode defaults to dontAsk. Use plan or acceptEdits only for the requested native behavior. The adapter does not expose bypass modes or interactive permission brokerage. dontAsk is not a filesystem sandbox: existing native configuration still applies. Host Full Shell never silently changes Claude permissions.

Check completed, state and is_error together. A final event alone is insufficient: success also requires native exit and confirmed owned-process cleanup. Read final_event for native error/usage fields. Event truncation, missed cursors and oversized-result errors must not be hidden. Credentials, setup tokens, login and vendor updates remain user-owned local operations.
