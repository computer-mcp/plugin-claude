# Package architecture

This repository owns the Claude Code CLI description and print/stream-json-to-MCP adapter. Computer MCP owns admission, host grants, workspace selection, CLI encoding and audit. The package neither links Computer MCP Core nor modifies host state or requires Host Services.

`computer-mcp-plugin.toml` combines a canonical file-backed CLI tree, the stdio adapter and Skills. `cli-tree.json` owns the exact supported native command/version contract. `bin/claude-mcp-adapter` owns run handles, retained native events and final results, cancellation and explicit native permission modes. Native conversation persistence stays with Claude Code; no duplicate vendor session database is created.

`bin/plugin_runtime.py` is this package's private standard-library runtime for bounded MCP I/O, validation, process supervision and retention. It is shipped with the plugin, not loaded from another plugin or host implementation module. Python 3.13+ must be available on the launch PATH. A separate supervisor lifeline and positive cleanup receipt distinguish process exit from confirmed cleanup. These are internal process mechanisms, not a new host contribution type.

The documented headless CLI is the selected upstream interface; the full Agent SDK's interactive callbacks and hosted Managed Agents are not substituted or claimed. Tests use deterministic peers and controlled process trees. Scripts validate real native version/help, deterministic archives and the unchanged host in isolated standalone mode. Authenticated backend execution and production activation require separate evidence.
