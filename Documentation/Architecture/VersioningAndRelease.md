# Versioning and Release

This document owns plugin-claude's version sources, compatibility baseline and
acceptance checks. The organization's
[VERSIONING.md](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md)
owns shared version, plugin API, release contents and publication rules.
The repository's [release guide](../Reference/Release.md) describes the
`release.yml` entry point and manual acceptance.

## Components and Version Authority

| Shipped component | Version meaning | Authoritative source | Derived fields | Update and read-only check |
| --- | --- | --- | --- | --- |
| `claude.zip` plugin package | Plugin package version | `version` in `computer-mcp-plugin.toml` | adapter `--version`, builder receipt, tag `vX.Y.Z`, `release-receipt.json`, catalog entry | Edit the manifest; `Tests/test_package.py` checks the packaged adapter's `--version` |

The archive contains the manifest, `cli-tree.json`, `bin/`, `skills/`, the README,
contribution guide, license, notices, `Documentation/` and `Examples/`.
Tests, build scripts and workflows are excluded from the archive.

## Dependencies and Verified Combinations

The package uses the Python standard library only and requires Python 3.13 or
newer on the host launch PATH. CI runs the tests on Python 3.13 and 3.14 and
checks that 3.11 and 3.12 are rejected before any vendor process starts.

The manifest declares `plugin_api = 1`; `[compatibility]` declares the minimum
Computer MCP host and supported architectures. Changes to the host baseline
require validation against the selected host.

`cli-tree.json` pins the exact Claude Code version through its
`executable_checks`, which the host applies before every CLI and adapter call. A
different vendor version requires a reviewed update of the tree, verified with
`Scripts/validate_native.py` against the real executable.

## Derived Metadata and Drift Checks

`Scripts/build_package.py` verifies the plugin ID, parses the CLI tree, and
produces the same archive bytes from the same source. Its builder receipt prints
the ID, version and SHA-256. The release caller passes this builder to the shared
release workflow.

`bin/plugin_runtime.py` is copied from the organization's canonical runtime.
The `runtime` job in `ci.yml` verifies its digest against the pinned
`plugin-runtime.yml`; runtime updates and that workflow pin move together.

## Candidate, Acceptance and Publication

The release caller selects `claude-plugin-${commit}-3.13` from `ci.yml` for a
reviewed `master` commit. It runs `python3 Scripts/build_package.py` through the
shared release workflow, which supplies the output directory. Manual acceptance
uses the dry-run bundle's exact archive and requires the native version and help
check and `Scripts/validate_host.py` against the selected Computer MCP release.
Authenticated model execution and production installation are separate checks
and are never implied by these results. Manual results and their limits are
recorded in the Release notes.

`release.yml` calls this repository's `notify-catalog.yml` only when publication
was requested and the shared workflow reports `published`. Only that notifier
job receives the catalog secret.

## Evidence Reuse and Invalidation

The CI artifact name binds the source commit and Python version. An archive
whose digest matches the accepted one keeps its acceptance. Any change to a
packaged file produces a new archive that needs the affected checks again.

## Entry Points and Artifact Retention

| Operation | Existing command or explicit manual procedure | Required access |
| --- | --- | --- |
| Version update and check | Edit `computer-mcp-plugin.toml`; `python3 -m unittest discover -s Tests -p 'test_*.py'` | Local checkout |
| Candidate validation and build | `ci.yml`; locally `python3 Scripts/build_package.py dist` | CI or local checkout |
| Status and interrupted-run recovery | Rerun the failed job; follow [Release](../Reference/Release.md#retry) for publication recovery | Repository Actions |
| Acceptance and publication | `release.yml` and manual checks in [Release](../Reference/Release.md) | Signing key and release write access |
| Cleanup | Delete local build output and evidence under ignored `dist/`, and `package-receipt.json` | Local checkout |

The builder refuses to overwrite a different archive, and `validate_host.py`
requires a new evidence directory. Remove obsolete build output before rebuilding
changed source; keep local build output and evidence under ignored `dist/`.
