import json
import tempfile
import time
import unittest
from support import Client


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.client=Client(self.temp.name);self.addCleanup(self.client.close)
    def value(self,response):
        self.assertFalse(response['result']['isError'],response)
        return Client.value(response)
    def call(self,name,args=None,timeout=10):return self.client.call('claude.'+name,args,timeout)
    def test_stream_json_through_mcp(self):
        r=self.value(self.call('run',{'prompt':'hello','permission_mode':'plan'}))
        self.assertEqual(r['result'],'hello');self.assertEqual(r['permission_mode'],'plan')
        self.assertEqual(r['final_event']['observed_permission_mode'],'plan')
    def test_resume_preserves_native_session_identity(self):
        r=self.value(self.call('run',{'prompt':'hello','resume_session_id':'saved-session'}))
        self.assertEqual(r['session_id'],'saved-session')
    def test_bypass_permissions_is_rejected(self):
        r=self.call('run',{'prompt':'hello','permission_mode':'bypassPermissions'})
        self.assertTrue(r['result']['isError'])
        self.assertEqual(Client.value(r)['error']['code'],'invalid_arguments')
    def test_async_start_event_result_and_cancel(self):
        r=self.value(self.call('run.start',{'prompt':'slow'}));run=r['run_id']
        self.assertFalse(r['completed'])
        self.assertIn(run,[x['run_id'] for x in self.value(self.call('run.list'))['runs']])
        self.value(self.call('run.cancel',{'run_id':run}))
        for _ in range(100):
            response=self.call('run.result',{'run_id':run})
            if Client.value(response).get('state')=='cancelled':break
            time.sleep(.03)
        else:self.fail('Run did not settle cancellation')
        self.assertTrue(response['result']['isError'])
    def test_mcp_cancellation_terminates_vendor_process(self):
        identifier=self.client.begin('claude.run',{'prompt':'slow'})
        time.sleep(.3)
        self.client.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':identifier}})
        r=self.client.wait(identifier)
        self.assertTrue(r['result']['isError']);self.assertEqual(Client.value(r)['state'],'cancelled')
    def test_nonzero_exit_preserves_final_vendor_error(self):
        r=self.call('run',{'prompt':'error-exit'})
        self.assertTrue(r['result']['isError'])
        value=Client.value(r)
        self.assertEqual(value['exit_code'],2);self.assertTrue(value['final_event']['is_error'])
    def test_missing_final_event_is_not_success(self):
        self.assertEqual(Client.value(self.call('run',{'prompt':'missing'}))['error']['code'],'vendor_failed')
    def test_final_result_does_not_hide_a_hanging_process(self):
        r=self.call('run',{'prompt':'hang-after-final','timeout_seconds':1})
        self.assertTrue(r['result']['isError']);self.assertEqual(Client.value(r)['error']['code'],'timeout')
    def test_oversized_unterminated_line_fails_promptly(self):
        started=time.monotonic()
        value=Client.value(self.call('run',{'prompt':'huge','timeout_seconds':5}))
        self.assertEqual(value['error']['code'],'frame_too_large');self.assertLess(time.monotonic()-started,4)
    def test_oversized_final_result_is_not_truncated_success(self):
        self.assertEqual(Client.value(self.call('run',{'prompt':'huge-final'}))['error']['code'],'result_too_large')
    def test_flood_is_bounded_and_paginates(self):
        r=self.value(self.call('run',{'prompt':'flood'}))
        self.assertTrue(r['events_truncated']);self.assertLess(len(json.dumps(r)),524288)
        page=self.value(self.call('run.events',{'run_id':r['run_id'],'max_bytes':1024}))
        self.assertTrue(page['missed_events']);self.assertGreater(page['next_cursor'],0)
    def test_invalid_uuid_and_relationships_fail_before_run(self):
        for args in [{'session_id':'x'*36},{'resume_session_id':'one','continue_previous':True},{'resume_session_id':'one','no_session_persistence':True}]:
            self.assertEqual(Client.value(self.call('run',dict(prompt='hello',**args)))['error']['code'],'invalid_arguments')
    def test_malformed_vendor_json_is_reported(self):
        self.assertEqual(Client.value(self.call('run',{'prompt':'malformed'}))['error']['code'],'invalid_vendor_response')
    def test_connection_does_not_adopt_foreign_run_ids(self):
        self.assertEqual(Client.value(self.call('run.result',{'run_id':'unknown'}))['error']['code'],'unknown_run')

if __name__=='__main__':unittest.main()
