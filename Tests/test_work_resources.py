"""Run retention must not discard native cleanup ownership."""
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import Mock, patch
from test_completion import adapter
from test_review_regressions import Peer, FINAL
from support import Client
from plugin_runtime import CONTINUATION_METADATA, Failure, Job, MCPServer, Process, WORK_INVOCATION, WORK_METADATA, WORK_URI


class WorkResourceTests(unittest.TestCase):
    def call(self,client,name,arguments=None,origin=None):
        params = {'name':name,'arguments':arguments or {}}
        if origin is not None: params['_meta'] = {WORK_INVOCATION:origin}
        return client.request('tools/call',params)

    def snapshot(self,client):
        result = client.request('resources/read',{'uri':WORK_URI})
        self.assertNotIn('error',result)
        content = result['result']['contents']
        self.assertEqual(len(content),1)
        self.assertEqual(content[0]['uri'],WORK_URI)
        return json.loads(content[0]['text'])

    def settled(self,client,run):
        deadline = time.monotonic()+5
        while time.monotonic()<deadline:
            result = Client.value(self.call(client,'claude.run.result',{'run_id':run}))
            if result.get('completed'): return result
            time.sleep(.01)
        self.fail('Run did not settle')

    def completed(self, identifier, cleanup_error=None):
        run = adapter.Run(identifier, {'prompt':'fixture'})
        with patch.object(adapter,'verify_version'),patch.object(adapter,'Process',return_value=Peer([FINAL],cleanup_error=cleanup_error)):
            run.work('/unused')
        return run

    def test_result_capacity_never_evicts_uncertain_cleanup(self):
        claude = adapter.Claude('/unused')
        uncertain = self.completed('uncertain',Failure('cleanup_unconfirmed','Missing native cleanup acknowledgement'))
        claude.runs[uncertain.id] = uncertain
        for index in range(31):
            run = self.completed(str(index))
            claude.runs[run.id] = run
        with patch.object(adapter,'resolve_executable',return_value='/unused'),patch.object(adapter.Run,'work'):
            claude.start({'prompt':'fixture'},Job())
        self.assertIn('uncertain',claude.runs)
        self.assertNotIn('0',claude.runs)
        self.assertEqual(len(claude.runs),32)

    def test_version_probe_failure_retains_cleanup_evidence(self):
        probe = Mock()
        expected = next(row['stdout'] for row in adapter.TREE['executable_checks'] if row['args']==['--version'])
        probe.read.side_effect = [expected.encode(),None]
        probe.finish.return_value = 0
        probe.close.side_effect = Failure('cleanup_unconfirmed','Probe cleanup acknowledgement missing')
        run = adapter.Run('probe',{'prompt':'fixture'})
        with patch('plugin_runtime.Process',return_value=probe),patch.object(adapter,'Process') as native:
            run.work('/unused')
            native.assert_not_called()
        self.assertTrue(run.done.is_set())
        self.assertEqual(run.result().get('cleanup_error',{}).get('code'),'cleanup_unconfirmed')
        self.assertFalse(run.execution_finished())

    def test_completed_results_remain_owned_until_explicit_release(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Client(directory)
            try:
                catalog = client.request('tools/list')['result']['tools']
                self.assertEqual(len(catalog),7)
                self.assertTrue(all(t['_meta'][WORK_METADATA]=={'format_version':1,'uri':WORK_URI} for t in catalog))
                declared = {tool['name']:tool['_meta'][CONTINUATION_METADATA]
                            for tool in catalog if CONTINUATION_METADATA in tool['_meta']}
                self.assertEqual(set(declared),{
                    'claude.run.result','claude.run.events','claude.run.cancel','claude.run.release',
                })
                for selector in declared.values():
                    self.assertEqual(selector,{'format_version':1,'selectors':[
                        {'kind':'claude.run','handles':{'id':'/run_id'}}]})
                self.assertEqual(client.request('resources/list')['result']['resources'][0]['uri'],WORK_URI)
                empty = self.snapshot(client)
                origin = str(uuid.uuid4())
                result = Client.value(self.call(client,'claude.run',{'prompt':'hello'},origin))
                self.assertTrue(result['completed'])
                self.assertTrue(result['cleanup_confirmed'])
                run = result['run_id']
                owned = self.snapshot(client)
                self.assertEqual(owned['instance_id'],empty['instance_id'])
                self.assertGreater(owned['revision'],empty['revision'])
                self.assertEqual(owned['resources'],[{'kind':'claude.run','id':run,'acquired_by':origin,'state':'active'}])
                for _ in range(2):
                    self.assertEqual(Client.value(self.call(client,'claude.run.result',{'run_id':run},str(uuid.uuid4())))['result'],'hello')
                    self.call(client,'claude.run.events',{'run_id':run})
                    self.assertEqual(self.snapshot(client),owned)
                released = self.call(client,'claude.run.release',{'run_id':run},str(uuid.uuid4()))
                self.assertEqual(Client.value(released),{'run_id':run,'released':True})
                self.assertEqual(self.snapshot(client)['resources'],[])
                self.assertGreater(self.snapshot(client)['revision'],owned['revision'])
                for tool in ('claude.run.result','claude.run.events','claude.run.release'):
                    self.assertEqual(Client.value(self.call(client,tool,{'run_id':run}))['error']['code'],'unknown_run')
                resumed = Client.value(self.call(client,'claude.run',{'prompt':'hello','resume_session_id':result['session_id']},str(uuid.uuid4())))
                self.assertEqual(resumed['session_id'],result['session_id'])
            finally: client.close()

    def test_identical_concurrent_runs_keep_distinct_origins_through_cancel(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Client(directory)
            try:
                requests = []
                for _ in range(2):
                    origin = str(uuid.uuid4())
                    client.serial += 1
                    requests.append((client.serial,origin))
                    client.send({'jsonrpc':'2.0','id':client.serial,'method':'tools/call','params':{'name':'claude.run.start','arguments':{'prompt':'slow'},'_meta':{WORK_INVOCATION:origin}}})
                owners = {Client.value(client.wait(key))['run_id']:origin for key,origin in requests}
                self.assertEqual({row['id']:row['acquired_by'] for row in self.snapshot(client)['resources']},owners)
                for run in owners:
                    rejected = Client.value(self.call(client,'claude.run.release',{'run_id':run}))
                    self.assertEqual(rejected['error']['code'],'run_active')
                    self.call(client,'claude.run.cancel',{'run_id':run})
                    self.assertTrue(self.settled(client,run)['cleanup_confirmed'])
                self.assertEqual({row['id']:row['acquired_by'] for row in self.snapshot(client)['resources']},owners)
                for run in owners: self.call(client,'claude.run.release',{'run_id':run})
                self.assertEqual(self.snapshot(client)['resources'],[])
            finally: client.close()

    def test_unbound_clients_work_but_cannot_claim_complete_live_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Client(directory)
            try:
                run = Client.value(client.call('claude.run',{'prompt':'hello'}))['run_id']
                self.assertIn('error',client.request('resources/read',{'uri':WORK_URI}))
                self.assertFalse(client.call('claude.run.release',{'run_id':run})['result']['isError'])
                self.assertEqual(self.snapshot(client)['resources'],[])
            finally: client.close()

    def test_invalid_correlation_and_forged_arguments_never_reserve_work(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Client(directory)
            try:
                for meta in (None,[],{WORK_INVOCATION:3},{WORK_INVOCATION:'invalid'}):
                    self.assertEqual(client.request('tools/call',{'name':'claude.run.start','arguments':{'prompt':'hello'},'_meta':meta})['error']['code'],-32602)
                self.assertTrue(client.call('claude.run.start',{'prompt':'hello','work_invocation':str(uuid.uuid4())})['result']['isError'])
                self.assertEqual(self.snapshot(client)['resources'],[])
                self.assertEqual(client.request('resources/read',{'uri':WORK_URI+'/unknown'})['error']['code'],-32602)
                self.assertEqual(client.request('ping')['result'],{})
            finally: client.close()

    def test_uncertain_work_limits_admission_and_survives_release_and_shutdown(self):
        claude = adapter.Claude('/unused')
        for index in range(4):
            run = self.completed(str(index),Failure('cleanup_unconfirmed','Missing acknowledgement'))
            run.work_invocation = str(uuid.uuid4())
            claude.runs[run.id] = run
        self.assertTrue(all(row['state']=='uncertain' for row in claude.work_resources()))
        with patch.object(adapter,'resolve_executable',return_value='/unused'),patch.object(adapter.Run,'work') as work:
            with self.assertRaises(Failure) as error: claude.start({'prompt':'fixture'},Job())
            self.assertEqual(error.exception.code,'capacity')
            work.assert_not_called()
        with self.assertRaises(Failure) as error: claude.release({'run_id':'0'},Job())
        self.assertEqual(error.exception.code,'cleanup_unconfirmed')
        with self.assertRaises(Failure): claude.shutdown()
        self.assertEqual(len(claude.runs),4)

    def test_pending_version_startup_is_owned(self):
        claude = adapter.Claude('/unused')
        entered, finish = threading.Event(), threading.Event()
        origin = str(uuid.uuid4())
        def verify(*_):
            entered.set()
            if not finish.wait(3): raise AssertionError('Fixture was not released')
            raise Failure('incompatible_vendor','No model process launched')
        with patch.object(adapter,'resolve_executable',return_value='/unused'),patch.object(adapter,'verify_version',side_effect=verify),patch.object(adapter,'Process') as process:
            run_id = claude.start({'prompt':'fixture'},Job(work_invocation=origin))['run_id']
            run = claude.get(run_id)
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(claude.work_resources(),[{'kind':'claude.run','id':run_id,'acquired_by':origin,'state':'active'}])
                self.assertFalse(run.execution_finished())
            finally:
                finish.set()
                run.thread.join(3)
            process.assert_not_called()
        self.assertTrue(run.execution_finished())
        self.assertEqual(len(claude.work_resources()),1)
        claude.release({'run_id':run_id},Job())
        self.assertEqual(claude.work_resources(),[])

    def test_settled_output_cannot_release_a_running_worker(self):
        claude = adapter.Claude('/unused')
        run = self.completed('owned')
        claude.runs[run.id] = run
        run.thread = Mock()
        run.thread.is_alive.return_value = True
        with self.assertRaises(Failure): claude.release({'run_id':run.id},Job())
        self.assertIn(run.id,claude.runs)
        run.thread.is_alive.return_value = False
        claude.release({'run_id':run.id},Job())
        self.assertEqual(claude.work_resources(),[])

    def test_worker_start_failure_does_not_leave_a_phantom_run(self):
        claude = adapter.Claude('/unused')
        with patch.object(adapter,'resolve_executable',return_value='/unused'),patch.object(threading.Thread,'start',side_effect=RuntimeError('Cannot start worker')):
            with self.assertRaises(Failure) as error: claude.start({'prompt':'fixture'},Job())
        self.assertEqual(error.exception.code,'startup_failed')
        self.assertEqual(claude.work_resources(),[])

    def test_partial_process_startup_keeps_unknown_cleanup(self):
        for confirmed in (True,False):
            with self.subTest(confirmed=confirmed):
                run = adapter.Run('partial',{'prompt':'fixture'})
                owners = []
                def close(process):
                    owners.append(process)
                    if not confirmed: raise Failure('cleanup_unconfirmed','Partial startup cleanup unavailable')
                try:
                    with patch.object(adapter,'verify_version'),patch('plugin_runtime.subprocess.Popen',return_value=Mock()),patch('plugin_runtime.os.set_blocking',side_effect=OSError('Fixture pipe setup failed')),patch.object(Process,'close',autospec=True,side_effect=close):
                        run.work('/unused')
                    self.assertEqual(len(owners),1)
                    self.assertTrue(run.done.is_set())
                    self.assertEqual(run.execution_finished(),confirmed)
                    self.assertEqual(run.work_resource()['state'],'active' if confirmed else 'uncertain')
                finally:
                    for owner in owners:
                        os.close(owner.life)
                        os.close(owner.receipt)

    def test_cleanup_io_failure_stays_failed_on_repeated_close(self):
        process = Process.__new__(Process)
        process.close_lock, process.writer_lock = threading.Lock(), threading.Lock()
        process.closed, process.cleanup_failure = False, None
        process.life, process.receipt = 100, 101
        process.child, process.output, process.stderr_thread = Mock(), Mock(), Mock()
        process.stop_stderr = threading.Event()
        def close(fd):
            if fd==process.life: raise OSError('Fixture lifeline close failed')
        with patch('plugin_runtime.os.close',side_effect=close),patch.object(process,'confirm_cleanup') as confirmed:
            for _ in range(2):
                with self.assertRaises(Failure) as error: process.close()
                self.assertEqual(error.exception.code,'cleanup_unconfirmed')
            confirmed.assert_not_called()

    def test_invalid_report_preserves_snapshot_revision(self):
        row = {'kind':'claude.run','id':1,'acquired_by':str(uuid.uuid4()),'state':'active'}
        rows = [row]
        server = MCPServer('fixture','1',[],lambda:None,work=lambda:rows)
        def snapshot(): return json.loads(server.work_resource()['contents'][0]['text'])
        first = snapshot()
        rows.append(dict(row))
        with self.assertRaises(Failure): snapshot()
        rows.pop()
        self.assertEqual(snapshot(),first)
        rows.append(dict(row,id='1'))
        second = snapshot()
        self.assertGreater(second['revision'],first['revision'])
        self.assertEqual(len(second['resources']),2)
        rows.reverse()
        self.assertEqual(snapshot(),second)
        rows[0]['state']='uncertain'
        self.assertGreater(snapshot()['revision'],second['revision'])


if __name__=='__main__': unittest.main()
