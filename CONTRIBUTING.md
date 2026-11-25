# Contributing

Read the [architecture](docs/Architecture/README.md) and [interface contract](docs/Reference/Interface.md). Keep vendor-specific behavior in this repository and preserve the host manifest/CLITree/MCP boundaries.

CI runs these checks on Python 3.13 and 3.14; run them before opening a pull request:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/build_package.py /new/output/directory
```

CI also runs `python3 tests/check_runtime_rejection.py` on Python 3.11 and 3.12 to confirm that unsupported interpreters are refused. When changing the native interface, inspect the matching real executable and run `scripts/validate_native.py --executable PATH`. Never use authenticated model calls as ordinary unit tests.

Do not commit caches, local credentials or generated runtime state. Publishing a repository or release is a separate explicit action.

Contributions are licensed under this repository's [LICENSE](LICENSE),
FSL-1.1-ALv2.

For declaration changes, compare manifest MCP defaults/overrides with the actual
adapter catalog. Requirements belong only in the manifest. Keep CLI/Skills
admission deterministic and preserve native permission and retained-work rules.
The source consumer takes explicit clean full revisions and never edits the host
checkout; follow the installation guide. Its Swift companion needs separate
serialized host build/runtime acceptance. A lint pass is not that evidence.
Run `python3 scripts/validate_host.py --help` for the source driver and
`python3 scripts/validate_archive.py --help` for the separate archive check.
Do not choose a moving host reference or substitute archive results for provider
approval, container, worktree or revocation evidence.


Update the `mcp.vendor_execution.files` digests when a reviewed adapter input
changes. The package builder verifies them against the archive contents. Use
`scripts/validate_host.py --suite registered-print` for the exact Host pair.
