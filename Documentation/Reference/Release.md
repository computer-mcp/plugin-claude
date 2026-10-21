# Release

This guide covers publishing an accepted package and notifying the official
plugin catalog. [Versioning and Release](../Architecture/VersioningAndRelease.md)
owns this repository's version sources and acceptance checks. The organization's
[VERSIONING.md](https://github.com/computer-mcp/.github/blob/master/VERSIONING.md)
owns shared rules; its
[plugin release guide](https://github.com/computer-mcp/.github/blob/master/Documentation/Reference/PluginRelease.md)
describes the reusable workflow and recovery contract.

## Publish

Before the first release, the repository owner must enable GitHub release
immutability in the repository settings. The release workflow refuses publication
when that prerequisite is disabled or cannot be verified.

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
4. Create and push a signed annotated tag `vX.Y.Z` on the accepted commit.
   Record the manual acceptance results and their limits in a draft GitHub
   Release's notes for that tag, targeting the full commit SHA.
5. Dispatch `release.yml` with `ref` set to the version tag and `publish: true`.
   The shared workflow verifies the tag signature, manifest and CI provenance,
   rebuilds the archive, generates the receipt and checksums, and publishes the
   verified assets through the draft Release. The dependent notifier then
   requests catalog reconciliation.

The shared workflow generates deterministic `release-receipt.json` and
`SHA256SUMS` according to the organization schema. The receipt records source,
compatibility and artifact provenance; manual acceptance results belong in the
Release notes.

## Catalog notification

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

The website's notification action is pinned to a reviewed full commit. Publish
that website commit first, then update the pin here when adopting a change to
the notification contract.

A release published with a repository `GITHUB_TOKEN` does not trigger
release-event workflows. `release.yml` calls `notify-catalog.yml` as a dependent
job only when `publish` is true and the shared release workflow reports
`published`. Only that job receives `CATALOG_APP_PRIVATE_KEY`; a dry run does
not use the catalog secret.

## Retry

Retry a failed publication with **Re-run failed jobs**. The shared workflow
reuses the verified bundle or a draft's frozen receipt as described in its
[recovery guide](https://github.com/computer-mcp/.github/blob/master/Documentation/Reference/PluginRelease.md#run-and-recover).

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
