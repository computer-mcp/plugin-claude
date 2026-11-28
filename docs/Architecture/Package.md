# Package architecture

This repository owns the Claude Code CLI description and print/stream-json-to-MCP adapter. Computer MCP owns admission, host grants, project selection, CLI encoding and audit. The package neither links Computer MCP Core nor modifies host state or requires Host Services.

`computer-mcp-plugin.toml` combines a canonical file-backed CLI tree, the stdio adapter and Skills. `cli-tree.json` owns the exact supported native command/version contract. `bin/claude-mcp-adapter` owns run handles, retained native events and final results, cancellation and explicit native permission modes. Native conversation persistence stays with Claude Code; no duplicate vendor session database is created.

`bin/plugin_runtime.py` is this package's private standard-library runtime for bounded MCP I/O, validation, process supervision and retention. It is shipped with the plugin, not loaded from another plugin or host implementation module. Python 3.13+ must be available on the launch PATH. A separate supervisor lifeline and positive cleanup receipt distinguish process exit from confirmed cleanup. These are internal process mechanisms, not a new host contribution type.

The ordinary MCP work resource projects these same run owners, including
pending startup, uncertain cleanup and retained completed results. Correlation
is bound at run creation and is not an authorization grant. Confirmed worker
and process cleanup are prerequisites for result eviction or explicit release.
Reading a result has no release side effect. The adapter bounds and versions
complete snapshots; the host owns configuration generations and routing.

The documented headless CLI is the selected upstream interface; the full Agent SDK's interactive callbacks and hosted Managed Agents are not substituted or claimed. Tests use deterministic peers and controlled process trees. Separate scripts validate native version/help, deterministic archives, and exact clean host/plugin source snapshots with an isolated development registration. Authenticated backend execution and production activation require separate evidence.

The manifest owns provider purposes and MCP caller requirement maps. The host
reviews their digest, provisions containers, intersects caller/provider grants,
and creates/selects/removes worktrees. No private host-services declaration is
needed: the adapter does not own lifecycle callbacks. Retained work uses the
ordinary MCP work resource with its original acquisition identity.

`scripts/validate_host.py` exports explicit clean commits, injects the plugin-owned
Swift companion only into the exported host test target, and records a fresh run
nonce, exact source pair and completed cases. It never writes to either input
checkout or uses an installed App/control socket. Its subprocess groups, exported
sources and build directory are bounded and cleaned; logs and receipts remain in
the supplied evidence directory. Failure receipts distinguish export cleanup from
unverified fixture cleanup. The separate `scripts/validate_archive.py` owns archive
worker checks and makes no runtime-admission claim.


The installed stream entry point requires the private Host vendor execution channel.
The package's reviewed signature binds the dependency, print argv recipe and tool
effects. The adapter translates stream events and tracks its local run handles.
The Host owns each run's version probe, workload, process retirement and receipts.
The shared Python runtime continues to implement local process supervision for
direct standalone MCP clients.
