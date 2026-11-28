# Installation and validation

## Dependencies and configuration

The standalone process supervisor requires the macOS `os.waitid` interface exposed by Python 3.13+. Installed runs require a Computer MCP Host that supports managed print execution.

Install Claude Code 2.1.59 separately. The version assertion in `cli-tree.json` applies before CLI calls and adapter execution.

Provide Python 3.13 or newer as `python3` on the environment PATH that launches Computer MCP. The packaged executable uses `#!/usr/bin/env python3`. A host dependency binding alone does not rewrite this interpreter lookup. A supported interpreter is required even when the vendor executable is explicitly bound.

Install the ZIP through Computer MCP's plugin UI or owner CLI. Installation is not activation or a permission grant. Use `plugins list/show` to obtain the current revision and installation identity. Review `Examples/settings.json`, replace its placeholder paths, then configure the plugin through the same UI or `plugins configure` command. The `claude-code` dependency binding selects the vendor for the CLI and installed MCP contributions. Remove any MCP `args` executable override when migrating settings. Direct standalone MCP clients can supply `--executable` to `bin/claude-mcp-adapter`.

The example exposes this plugin's complete MCP tool catalog with no extra prefix. It is a host choice, not authorization embedded in the package. Authorize the desired tools/registration and project in the calling profile. Obtain projected CLI and MCP names from the actual host `tools/list`, rather than constructing names. `plugins doctor` checks files and configuration; an MCP connection check verifies initialization/catalog, not model execution.

Computer MCP publishes plugin configuration changes to connected clients atomically. New calls use the current configuration; existing work keeps its owning runtime until release. Installation does not grant access, and later calls use current authorization. Do not restart the active development control connection merely to test installation.

## Claude Code sign-in

For standalone Claude Code or direct use of `bin/claude-mcp-adapter`, run
`claude auth login` in a terminal with the same Claude Code account state as the
standalone process. The command signs in to the state selected by its launching
environment. [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference)

On a fresh Host install, you can bind the executable, configure and enable the
plugin, and check installation and tool discovery while signed out. Installed CLI
and MCP runs use the registered provider's isolated state, with a Host-managed
HOME, cache and state paths, plus per-execution scratch. A standalone terminal
login stays in the terminal's Claude Code state. The current Host and installed
plugin expose no command for first sign-in in the provider state, so authenticated
model runs remain unavailable on a fresh install.

In clean signed-out state, Claude Code 2.1.59 reports `loggedIn: false` and
`authMethod: "none"` from `claude auth status` and exits with status `1`.
Its print stream ends with a native result containing `is_error: true` and
`Not logged in · Please run /login`, also with exit status `1`. The MCP
result retains the final event and exit code.

During enablement, review the requested Claude API and authentication hosts.
The owner may narrow the list, and Host policy limits still apply. See the
[sandbox contract](Interface.md#reviewed-declarations-and-caller-admission).

## Build

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/validate_native.py --executable /absolute/path/to/claude
python3 scripts/build_package.py /new/output/directory
```

The builder produces `claude.zip` and prints an ID/version/SHA-256 receipt. Identical source bytes produce identical archive bytes. It refuses to overwrite a different existing artifact. The archive contains the manifest, reviewed vendor signature and file digests, canonical CLI tree, adapters, Skills, examples, manuals and notices. README images are included at `.github/assets/logo/logo-light.png` and `.github/assets/logo/logo-dark.png`, preserving their relative links. These are the only packaged `.github` files. It excludes tests, build scripts, local evidence, caches and credentials. Only executable entrypoints receive executable mode.

CI runs deterministic fixture tests and packaging. Native validation checks the
installed version, help and required flags. Authenticated prompt execution can
consume subscription or API usage and perform vendor actions, so it requires
separate authorization.

## Isolated source interoperability

Run the deterministic companion against explicit clean source commits. Both
inputs must be repository roots whose HEAD exactly matches the supplied lowercase
40-character SHA, including no untracked changes. Pass `--output` an absolute
path for a new evidence directory. The path must be unused and must neither be
inside nor contain either source checkout. The driver creates the directory and
stages snapshots there without editing either checkout.

```sh
python3 scripts/validate_host.py \
  --host-source /absolute/path/to/host-source --host-sha '<full-host-sha>' \
  --plugin-source /absolute/path/to/plugin-source --plugin-sha '<full-plugin-sha>' \
  --suite registered-print \
  --output /absolute/path/to/evidence/claude-registered-print
```

This requires the matched host macOS test target and its existing isolated
permission/lifecycle helpers, Swift, and Python 3.13+. It builds only the exported
host using native SwiftPM and an isolated scratch path. Native vendor behavior is
replaced by the inert fixture; the selected Python interpreter is recorded.
The registered print selector builds the archive from the pinned plugin snapshot,
installs and selects it in an isolated Host fixture, and records the archive SHA.
It exercises stdin EOF, addressed cancellation, a concurrent sibling run,
native final event and nonzero exit retention, and release. The `source`
selector exercises development registration, CLI/MCP/Skills, caller and provider
grants, worktree boundaries, container persistence, revocation and removal. Case evidence must have a fresh nonce, an
executed test count above zero and the complete exact case set. A passing receipt
requires command success and source readback as well as case evidence.

The integration owner serializes Host builds and runs the registered selector
against the exact Host candidate that defines managed print execution.

## Isolated archive validation

Archive structure has a separate driver and does not substitute for source
admission or native usability evidence:

```sh
python3 scripts/validate_archive.py \
  --host /absolute/path/to/candidate/computer-mcp \
  --expected-host-version <host-version> \
  --archive /output/claude.zip --output /new/evidence/directory
```

It uses the selected host's archive worker and isolated temporary storage, never
the production control socket. It checks manifest/tree identity, executable mode
and cache exclusion. Archive and native checks are separate acceptance steps.

## Result interpretation

Fixture success proves adapter protocol/ownership behavior against the tested peer, not a real account or model. A native version/help check proves the installed command surface, not backend availability. An exact-source isolated consumer proves interoperability for the recorded pair and exercised cases; it is not production installation or public release evidence. Keep these results separate in delivery receipts.
