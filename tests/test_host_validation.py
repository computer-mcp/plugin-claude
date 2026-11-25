"""Source-driver boundaries and inert native peer; no host build or vendor calls."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('validate_host', ROOT / 'scripts/validate_host.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
peer_spec = importlib.util.spec_from_file_location('host_vendor', ROOT / 'tests/Fixtures/host_vendor.py')
peer = importlib.util.module_from_spec(peer_spec)
peer_spec.loader.exec_module(peer)


class SourceDriverTests(unittest.TestCase):
    def test_full_commit_and_absolute_inputs(self):
        self.assertEqual(driver.revision('a' * 40), 'a' * 40)
        for value in ('master', 'a' * 39, 'A' * 40, 'HEAD'):
            with self.assertRaises(argparse.ArgumentTypeError):
                driver.revision(value)
        with self.assertRaises(argparse.ArgumentTypeError):
            driver.absolute('relative')

    def test_dirty_or_mismatched_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for answers in ([str(root), 'b'*40], [str(root), 'a'*40, ' M manifest']):
                with patch.object(driver, 'git', side_effect=answers):
                    with self.assertRaises(ValueError):
                        driver.verify_source(root, 'a'*40)
            with patch.object(driver, 'git', side_effect=[str(root), 'a'*40, '']):
                driver.verify_source(root, 'a'*40)

    def test_output_and_inputs_cannot_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for host, plugin, output in [(root/'h', root/'h/p', root/'o'),
                                          (root/'h', root/'p', root/'p/o'),
                                          (root/'h', root/'p', root)]:
                with self.assertRaises(ValueError):
                    driver.validate_locations(host, plugin, output)
            driver.validate_locations(root/'h', root/'p', root/'o')

    def test_export_refuses_links_traversal_and_preserves_modes(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE),
                           ('regular', tarfile.REGTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                archive = Path(temp)/'source.tar'
                with tarfile.open(archive, 'w') as stream:
                    item = tarfile.TarInfo(name); item.type = kind; item.mode = 0o755
                    item.size = 1 if kind == tarfile.REGTYPE else 0
                    stream.addfile(item, io.BytesIO(b'x') if item.size else None)
                target = Path(temp)/'snapshot'
                if name == 'regular':
                    driver.extract_source(archive, target)
                    self.assertEqual((target/name).read_bytes(), b'x')
                    self.assertEqual((target/name).stat().st_mode & 0o777, 0o755)
                else:
                    with self.assertRaises(ValueError):
                        driver.extract_source(archive, target)

    def test_evidence_requires_fresh_nonzero_exact_cases(self):
        valid = {'kind':'deterministic','run_id':'fresh','tests_executed':1,
                 'cases':sorted(driver.CASES)}
        driver.validate_evidence(valid, 'fresh')
        for changes in ({'tests_executed':0}, {'tests_executed':True}, {'run_id':'stale'},
                        {'cases':[]}, {'cases':sorted(driver.CASES)*2}):
            with self.assertRaises(ValueError):
                driver.validate_evidence(dict(valid, **changes), 'fresh')

    def test_process_exit_timeout_and_log_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            driver.run_process([sys.executable, '-c', 'print(1)'], root, dict(os.environ), root/'ok', 2)
            self.assertEqual((root/'ok').read_text().strip(), '1')
            with self.assertRaises(RuntimeError):
                driver.run_process([sys.executable, '-c', 'raise SystemExit(3)'], root, dict(os.environ), root/'failure', 2)
            with self.assertRaises(TimeoutError):
                driver.run_process([sys.executable, '-c', 'import time;time.sleep(30)'], root, dict(os.environ), root/'timeout', .1)
            with self.assertRaises(RuntimeError):
                driver.run_process([sys.executable, '-c', 'import sys;sys.stdout.write("x"*(33*1024*1024))'], root, dict(os.environ), root/'overflow', 3)

    def test_cli_help_and_missing_inputs(self):
        command = [sys.executable, str(ROOT/'scripts/validate_host.py')]
        self.assertEqual(subprocess.run(command+['--help'], capture_output=True, timeout=3).returncode, 0)
        self.assertEqual(subprocess.run(command, capture_output=True, timeout=3).returncode, 2)

    def test_failed_run_cleans_staged_snapshots_and_records_exact_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            host=root/'host'; plugin=root/'plugin'; host.mkdir(); plugin.mkdir()
            for name in driver.INPUTS:
                path=plugin/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('input')
            args=argparse.Namespace(host_source=host, plugin_source=plugin, host_sha='a'*40,
                                    plugin_sha='b'*40, output=root/'run', timeout=1, suite='source')
            def export(source, sha, destination, environment, output):
                destination.mkdir()
                if destination.name=='host-source':
                    (destination/'Tests/ComputerMCPMacOSTests').mkdir(parents=True)
                else:
                    for name in driver.INPUTS:
                        path=destination/name; path.parent.mkdir(parents=True,exist_ok=True)
                        path.write_bytes((plugin/name).read_bytes())
            with patch.object(driver,'verify_source'), patch.object(driver,'export_source',side_effect=export), patch.object(driver,'run_process',side_effect=RuntimeError('test failure')):
                with self.assertRaises(RuntimeError): driver.run(args)
            receipt=json.loads((args.output/'receipt.json').read_text())
            self.assertEqual((receipt['host_sha'],receipt['plugin_sha']),('a'*40,'b'*40))
            self.assertEqual(receipt['status'],'failed')
            self.assertFalse((args.output/'host-source').exists())
            self.assertFalse((args.output/'plugin-source').exists())

    def test_cli_peer_accepts_canonical_equals_options(self):
        with tempfile.TemporaryDirectory() as temp:
            command = [sys.executable,str(ROOT/'tests/Fixtures/host_vendor.py'),'-p',
                       '--output-format=json','--permission-mode=dontAsk','--','cli']
            result=subprocess.run(command,cwd=temp,capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['result'],'cli')

    def test_native_peer_preserves_explicit_mode_session_and_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            arguments=['--permission-mode','plan','--output-format','stream-json',
                       '--resume=saved-session','--',"--leading 'quote' 中文\ntext"]
            result=subprocess.run([sys.executable,str(ROOT/'tests/Fixtures/host_vendor.py'),*arguments],cwd=temp,input="",capture_output=True,text=True,timeout=3)
            self.assertEqual(result.returncode,0,result.stderr)
            frame=json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(frame['session_id'],'saved-session')
            self.assertEqual(frame['observed_permission_mode'],'plan')
            self.assertEqual(json.loads((Path(temp)/'native-calls.jsonl').read_text())['argv'],arguments)


if __name__ == '__main__':
    unittest.main()
