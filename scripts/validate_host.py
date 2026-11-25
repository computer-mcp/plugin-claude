"""Run the deterministic Claude companion against explicit clean source commits.

The driver exports both commits into an external output directory. The registered
selector builds and installs the exact plugin archive into its fixture database. It never edits
input checkouts, contacts an installed App or launches the vendor's executable.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time

FIXTURE = "ClaudeSourceIntegrationTests.swift"
CASES = {
    "declarations", "development-registration", "dual-principal", "read-write",
    "cli", "mcp", "skills", "worktree-boundaries", "container-persistence",
    "continuation", "cancellation", "scoped-revocation", "host-removal", "cleanup",
}
REGISTERED_CASES = {
    "installed-reviewed-archive", "print-stdin-eof", "addressed-retirement",
    "independent-run", "native-final-and-exit", "retained-release",
}
SELECTORS = {
    "source": "ClaudeSourceIntegrationTests.sourceConsumerContract",
    "registered-print": "ClaudeSourceIntegrationTests.registeredManagedPrint",
}
INPUTS = (
    "computer-mcp-plugin.toml", "cli-tree.json",
    "tests/Fixtures/" + FIXTURE + ".txt", "tests/Fixtures/host_vendor.py",
    "bin/claude-mcp-adapter", "bin/claude-mcp-managed", "bin/claude_vendor_execution.py",
    "bin/plugin_runtime.py", "claude-vendor-execution.json",
    "scripts/build_package.py", "scripts/validate_host.py",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise argparse.ArgumentTypeError("Use a full lowercase 40-character commit SHA")
    return value


def absolute(value):
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Use an absolute path")
    return path.resolve()


def git(root, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=True,
        stderr=subprocess.PIPE, timeout=15).strip()


def verify_source(root, sha):
    revision(sha)
    if not root.is_dir() or git(root, "rev-parse", "--show-toplevel") != str(root):
        raise ValueError("Source must be an existing repository root")
    if git(root, "rev-parse", "HEAD") != sha:
        raise ValueError("Source HEAD differs from its supplied commit")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("Source checkout must be clean, including untracked files")


def contains(parent, child):
    return child == parent or parent in child.parents


def validate_locations(host, plugin, output):
    if contains(host, plugin) or contains(plugin, host):
        raise ValueError("Host and plugin must be separate, non-nested source checkouts")
    if any(contains(root, output) or contains(output, root) for root in (host, plugin)):
        raise ValueError("Output must be outside both source checkouts and their ancestors")
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new external directory")


def run_process(command, cwd, environment, log, timeout):
    """Bound execution/output and reap the driver-owned command group on every exit."""
    with log.open("wb") as stream:
        process = subprocess.Popen(
            command, cwd=cwd, env=environment, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + timeout
        failure = None
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Command exceeded its deadline")
                if log.stat().st_size > 32 * 1024 * 1024:
                    raise RuntimeError("Command exceeded its 32 MiB output bound")
                time.sleep(0.05)
            if process.returncode:
                raise RuntimeError(f"Command exited {process.returncode}; inspect {log}")
        except BaseException as error:
            failure = error
        finally:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                os.killpg(process.pid, signal.SIGKILL)
                if failure is None:
                    failure = RuntimeError("Command left descendants; its group was terminated")
            process.wait()
        if failure:
            raise failure
        if log.stat().st_size > 32 * 1024 * 1024:
            raise RuntimeError("Command exceeded its 32 MiB output bound")


def extract_source(archive, destination):
    """Export only bounded regular files and directories into a fresh directory."""
    if archive.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("Source archive exceeds 128 MiB")
    destination.mkdir()
    total = 0
    with tarfile.open(archive, "r:") as source:
        for index, entry in enumerate(source):
            target = destination / entry.name
            if (index >= 20000 or entry.name.startswith("/")
                    or ".." in Path(entry.name).parts or not contains(destination, target)
                    or not (entry.isdir() or entry.isfile())):
                raise ValueError("Unsafe or oversized source archive")
            total += entry.size
            if total > 128 * 1024 * 1024:
                raise ValueError("Expanded source exceeds 128 MiB")
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(entry) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                target.chmod(0o755 if entry.mode & 0o111 else 0o644)


def export_source(root, sha, destination, environment, output):
    archive = output / (destination.name + ".tar")
    run_process(
        ["git", "-C", str(root), "archive", "--format=tar", "--output", str(archive), sha],
        output, environment, output / (destination.name + "-export.log"), 30)
    try:
        extract_source(archive, destination)
    finally:
        archive.unlink(missing_ok=True)


def validate_evidence(observed, run_id, expected_cases=CASES):
    cases = observed.get("cases")
    if (observed.get("kind") != "deterministic" or observed.get("run_id") != run_id
            or type(observed.get("tests_executed")) is not int or observed["tests_executed"] < 1
            or not isinstance(cases, list) or len(cases) != len(expected_cases)
            or any(not isinstance(case, str) for case in cases) or set(cases) != expected_cases):
        raise ValueError("Consumer case evidence is incomplete, duplicated or stale")


def run(args):
    suite = args.suite
    validate_locations(args.host_source, args.plugin_source, args.output)
    verify_source(args.host_source, args.host_sha)
    verify_source(args.plugin_source, args.plugin_sha)
    before = {name: digest(args.plugin_source / name) for name in INPUTS}
    args.output.mkdir(parents=True)
    output = args.output
    host = output / "host-source"
    plugin = output / "plugin-source"
    evidence = output / "cases.json"
    run_id = os.urandom(16).hex()
    result = {
        "host_sha": args.host_sha, "plugin_sha": args.plugin_sha,
        "inputs_sha256": before, "run_id": run_id, "kind": "deterministic", "suite": suite,
        "native_verified": False, "status": "failed", "cleanup": "pending",
        "python": str(Path(sys.executable).resolve()), "python_version": sys.version,
    }
    environment = dict(os.environ)
    # No implicit Claude source, target or evidence selection from the parent session.
    for key in list(environment):
        if key.startswith("COMPUTER_MCP_CLAUDE_"):
            del environment[key]
    environment.update({
        "COMPUTER_MCP_CLAUDE_PLUGIN": str(plugin),
        "COMPUTER_MCP_CLAUDE_CASES": str(evidence),
        "COMPUTER_MCP_CLAUDE_RUN_ID": run_id,
        "COMPUTER_MCP_CLAUDE_PYTHON": str(Path(sys.executable).resolve()),
    })
    try:
        export_source(args.host_source, args.host_sha, host, environment, output)
        export_source(args.plugin_source, args.plugin_sha, plugin, environment, output)
        for name, expected in before.items():
            if digest(plugin / name) != expected:
                raise ValueError("Exported plugin differs from its source commit")
        target = host / "Tests/ComputerMCPMacOSTests" / FIXTURE
        if not target.parent.is_dir():
            raise ValueError("Host does not provide the required macOS test target")
        with target.open("xb") as destination:
            destination.write((plugin / INPUTS[2]).read_bytes())
        if suite == "registered-print":
            packages = output / "package"
            run_process(
                [sys.executable, "-B", str(plugin / "scripts/build_package.py"), str(packages)],
                plugin, environment, output / "package-build.log", 30)
            archive = packages / "claude.zip"
            result["archive_sha256"] = digest(archive)
            environment.update({
                "COMPUTER_MCP_CLAUDE_ARCHIVE": str(archive),
                "COMPUTER_MCP_CLAUDE_ARCHIVE_SHA256": result["archive_sha256"],
            })
        run_process(
            ["/usr/bin/swift", "test", "--build-system", "native", "--scratch-path",
             str(output / "build"), "--no-parallel", "--filter", SELECTORS[suite]],
            host, environment, output / "swift-test.log", args.timeout)
        if evidence.stat().st_size > 65536:
            raise ValueError("Case evidence exceeds its bound")
        observed = json.loads(evidence.read_text())
        validate_evidence(observed, run_id, REGISTERED_CASES if suite == "registered-print" else CASES)
        if {name: digest(args.plugin_source / name) for name in INPUTS} != before:
            raise ValueError("Source input changed during verification")
        result["cases"] = sorted(observed["cases"])
        result["tests_executed"] = observed["tests_executed"]
        result["status"] = "passed"
    finally:
        # Logs/case evidence survive; all exported sources and build output are owned here.
        for path in (host, plugin, output / "build"):
            if path.is_symlink():
                raise RuntimeError("Run-owned cleanup target was replaced by a symlink")
            if path.exists():
                shutil.rmtree(path)
        result["cleanup"] = ("confirmed" if result["status"] == "passed"
                             else "exports-removed; fixture-process-cleanup-unverified")
        try:
            verify_source(args.host_source, args.host_sha)
            verify_source(args.plugin_source, args.plugin_sha)
        except BaseException:
            result["status"] = "failed"
            raise
        finally:
            (output / "receipt.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"receipt": str(output / "receipt.json"), "status": "passed"}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-source", required=True, type=absolute)
    parser.add_argument("--host-sha", required=True, type=revision)
    parser.add_argument("--plugin-source", required=True, type=absolute)
    parser.add_argument("--plugin-sha", required=True, type=revision)
    parser.add_argument("--output", required=True, type=absolute)
    parser.add_argument("--suite", choices=SELECTORS, default="source")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 1800:
        parser.error("--timeout must be between 1 and 1800 seconds")
    try:
        run(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Source verification failed: {error}\n")


if __name__ == "__main__":
    main()
