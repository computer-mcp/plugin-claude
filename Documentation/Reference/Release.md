# Release

Release status: [CI](https://github.com/computer-mcp/plugin-claude/blob/master/.github/workflows/ci.yml)
builds candidate archives on pull requests, `master` pushes and manual runs.
[`release.yml`](https://github.com/computer-mcp/plugin-claude/blob/master/.github/workflows/release.yml)
implements dry runs and publication; native and host acceptance are manual.

The organization [VERSIONING](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md)
owns version rules, including tags, version choice and the changelog. This
reference records this repository's version sources, compatibility, release
procedure and checks. The shared
[release workflow guide](https://github.com/computer-mcp/github-workflows/blob/master/docs/plugin-release.md)
describes workflow verification and recovery.

## Components and Version Sources

| Shipped component | Version meaning | Version source | Mirrors and derived fields | Update and read-only check |
| --- | --- | --- | --- | --- |
| `claude.zip` plugin package | Package version | `version` in [`computer-mcp-plugin.toml`](../../computer-mcp-plugin.toml) | adapter `--version`, builder receipt, release tag, `release-receipt.json`, catalog entry | Edit the manifest; `Tests/test_package.py` checks the packaged adapter's `--version` |

The archive contains the manifest, `cli-tree.json`, `bin/`, `skills/`, the README,
contribution guide, license, notices, `Documentation/` and `Examples/`.
Tests, build scripts and workflows are excluded from the archive.

## Compatibility Surface

The package contributes a file-backed CLI tree, stdio MCP adapter and Skills.
[Interface](Interface.md) owns the CLI argv and output mapping, MCP tools and
resources, session and permission semantics, retention, cancellation and errors.
The manifest owns `plugin_api` and the minimum host and architecture declarations
in `[compatibility]`. Validate changes to those bounds against the selected host.

## Dependencies and Verified Combinations

The package uses the Python standard library only and requires Python 3.13 or
newer on the host launch PATH. CI runs the tests on Python 3.13 and 3.14 and
checks that 3.11 and 3.12 are rejected before any vendor process starts.

`cli-tree.json` pins the exact Claude Code version through its
`executable_checks`, applied before projected CLI calls and adapter execution.
A different vendor version requires a reviewed tree update verified with
`Scripts/validate_native.py` against the real executable. Native version/help,
fixture protocol, selected-host interoperability and authenticated execution
are separate evidence classes; see [Installation](Installation.md).

## Derived Metadata and Drift Checks

`Scripts/build_package.py` verifies the plugin ID, parses the CLI tree, and
produces the same archive bytes from the same source. Its builder receipt prints
the ID, version and SHA-256. The release caller passes this builder to the shared
release workflow.

`bin/plugin_runtime.py` is copied from the organization's canonical runtime.
The `runtime` job in `ci.yml` verifies its digest against the pinned
`plugin-runtime.yml`; runtime updates and that workflow pin move together.

## Candidate, Acceptance and Publication

Publication depends on the repository's GitHub release immutability setting.
The shared workflow checks that setting before writing a Release.

### Publish

1. Confirm that `version` in `computer-mcp-plugin.toml` has not been released
   and that the reviewed `master` commit has a successful `ci.yml` push run.
2. Dispatch `.github/workflows/release.yml` with `ref` set to that full commit
   SHA and `publish: false` (the default). It rebuilds with
   `python3 Scripts/build_package.py`, compares against the exact
   `claude-plugin-<commit>-3.13` CI artifact and uploads
   `plugin-release-<run-id>-<attempt>`. Inspect its `assets/` directory for
   `claude.zip`, `release-receipt.json` and `SHA256SUMS`. An untagged dry run
   reports the signed annotated tag still required for publication.
3. Run the native and isolated host checks in
   [Installation](Installation.md#isolated-host-interoperability) against that
   exact `claude.zip`. Keep authenticated execution and production installation
   results separate from fixture and non-model checks.
4. Create and push the version tag that [VERSIONING](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md) requires on the accepted commit.
   Record the manual acceptance results and their limits in a draft GitHub
   Release's notes for that tag, targeting the full commit SHA.
5. Dispatch `release.yml` with `ref` set to the version tag and `publish: true`.
   The shared workflow verifies the tag signature, manifest and CI provenance,
   rebuilds the archive, generates the receipt and checksums, and publishes the
   verified assets through the draft Release. The dependent notifier then
   requests catalog reconciliation.

The shared workflow generates the receipt and checksums; CI's
`package-receipt.json` remains builder metadata in the source CI artifact.

### Catalog notification

`notify-catalog.yml` runs when a release is published, edited, released,
unpublished or deleted, and on manual dispatch. It asks the website to reconcile
the complete catalog. The website verifies the actual GitHub releases rather
than the event payload, keeps verified history, and applies its own withdrawal
policy; an event never withdraws a release by itself.

The workflow authenticates as the receiver-scoped catalog GitHub App through
the `CATALOG_APP_CLIENT_ID` variable and the `CATALOG_APP_PRIVATE_KEY` secret.
The App needs Actions write access to `computer-mcp/computer-mcp.github.io` only.
The job checks this repository's immutable ID, does not check out package code,
and grants its own token no repository permissions. Missing or rejected
authority fails the run visibly.

The shared notification action is pinned to a reviewed full commit. Publish
that shared workflow commit first, then update the pin here when adopting a change to
the notification contract.

A release published with a repository `GITHUB_TOKEN` does not trigger
release-event workflows. `release.yml` calls `notify-catalog.yml` as a dependent
job only when `publish` is true and the shared release workflow reports
`published`. Only that job receives `CATALOG_APP_PRIVATE_KEY`; a dry run does
not use the catalog secret.

## Evidence Reuse and Invalidation

The CI artifact name identifies the source commit and Python version. The release
workflow verifies CI provenance and artifact digests; `release-receipt.json`
records the commit, CI run and attempt, artifact digest and archive SHA-256.

An archive with the accepted digest keeps its archive acceptance for the tested
combination. Reuse of manual results is reviewed against the native dependency,
selected host, check definitions and relevant environment recorded with them.
Changes to packaged files produce a new archive and require the affected checks
again. A check-only change can reuse unchanged archive bytes with fresh affected
checks. Source tests do not replace installation, native or authenticated
execution evidence. Keep failed-check output and result limits with the manual
acceptance record.

## Entry Points and Artifact Retention

| Operation | Existing command or explicit manual procedure | Required access |
| --- | --- | --- |
| Version update and check | Edit `computer-mcp-plugin.toml`; `python3 -m unittest discover -s Tests -p 'test_*.py'` | Local checkout |
| Candidate validation and build | `ci.yml`; locally `python3 Scripts/build_package.py dist` | CI or local checkout |
| Native acceptance | `python3 Scripts/validate_native.py --executable <claude>` | User-installed native executable |
| Exact archive host acceptance | `python3 Scripts/validate_host.py --host <computer-mcp> --expected-host-version X.Y.Z --archive dist/claude.zip --output <new-evidence-directory>`; see [Installation](Installation.md#isolated-host-interoperability) | Selected host binary and candidate archive |
| Acceptance and publication | Manual checks above; dispatch `release.yml`, dry run first | Repository Actions; publication also needs a signing key and release write access |
| Status and interrupted-run recovery | Inspect CI or `release.yml`; follow [Retry](#retry) | Repository Actions |
| Cleanup | Delete obsolete output and evidence under ignored `dist/`, and `package-receipt.json` | Local checkout |

The builder refuses to overwrite a different archive, and `validate_host.py`
requires a new evidence directory. Remove obsolete build output before rebuilding
changed source. Keep local output and evidence under ignored `dist/`; remove
them after use unless an acceptance record requires retention. CI sets no
per-artifact retention override.

### Retry

Retry a failed publication with **Re-run failed jobs**. The shared workflow
reuses the verified bundle or a draft's frozen receipt as described in its
[recovery guide](https://github.com/computer-mcp/github-workflows/blob/master/docs/plugin-release.md#run-and-recover).

For a missed or failed notification, rerun only the notifier job or dispatch:

```sh
gh workflow run notify-catalog.yml --repo computer-mcp/plugin-claude --ref master
```

A successful dispatch only proves the request was accepted. Follow the run's
`run_url` output to the website run, confirm it succeeded, and confirm the public
index lists the expected release. Retrying never requires changing or
republishing the release: reconciliation is idempotent, and the website's
hourly schedule also repairs missed notifications.

The website's
[catalog publication and notification contract](https://github.com/computer-mcp/computer-mcp.github.io/blob/master/docs/plugin-catalog.md)
covers provenance, credentials, retry bounds and deployment.
