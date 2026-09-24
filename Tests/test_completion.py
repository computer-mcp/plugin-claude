"""Completion semantics regressions without invoking a vendor or model."""
import importlib.machinery
import importlib.util
import sys
import unittest
from support import ROOT, VENDOR

sys.path.insert(0, str(ROOT / 'bin'))
from plugin_runtime import Failure, Job

loader = importlib.machinery.SourceFileLoader('completion_adapter', str(ROOT / f'bin/{VENDOR}-mcp-adapter'))
spec = importlib.util.spec_from_loader(loader.name, loader)
adapter = importlib.util.module_from_spec(spec)
loader.exec_module(adapter)


class CompletionTests(unittest.TestCase):
    def test_finished_run_explicitly_reports_completion(self):
        run = adapter.Run('local-run', {})
        run.value = {'is_error': False, 'run_id': run.id}
        run.state = 'completed'
        run.done.set()
        self.assertTrue(run.result()['completed'])


    def test_partial_messages_are_requested(self):
        command, _ = adapter.build_command('/unused', {'prompt': 'not-executed'})
        self.assertIn('--include-partial-messages', command)


if __name__ == '__main__':
    unittest.main()
