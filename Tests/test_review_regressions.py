"""Final result ownership when later stream or cleanup work fails."""
import unittest
from unittest.mock import patch
from test_completion import adapter
from plugin_runtime import Failure, Job, encoded

FINAL = {'type':'result','subtype':'success','is_error':False,
         'session_id':'native-session','result':'kept','extension':{'unknown':True}}

class Peer:
    def __init__(self, frames, finish_error=None, cleanup_error=None):
        self.frames=iter(frames)
        self.finish_error=finish_error
        self.cleanup_error=cleanup_error
    def end_input(self): pass
    def read(self, *_):
        item=next(self.frames,None)
        if isinstance(item,Exception): raise item
        return item if isinstance(item,bytes) or item is None else encoded(item)
    def finish(self, *_):
        if self.finish_error: raise self.finish_error
        return 0
    def close(self):
        if self.cleanup_error: raise self.cleanup_error

class ReviewRegressions(unittest.TestCase):
    def execute(self, peer):
        run=adapter.Run('owned-run',{'prompt':'fixture'})
        with patch.object(adapter,'verify_version'),patch.object(adapter,'Process',return_value=peer):
            run.work('/unused')
        return run.result()
    def test_cancel_during_admission_never_reserves_native_work(self):
        claude=adapter.Claude('/unused');job=Job()
        def resolve(*_):
            job.cancel()
            return '/unused'
        with patch.object(adapter,'resolve_executable',side_effect=resolve),patch.object(adapter.Run,'work') as work:
            with self.assertRaises(Failure) as error:claude.start({'prompt':'fixture'},job)
            self.assertEqual(error.exception.code,'cancelled')
            self.assertEqual(claude.runs,{})
            work.assert_not_called()

    def test_final_survives_later_failure_and_event_eviction(self):
        overflow=[{'type':'assistant','text':str(i)} for i in range(300)]
        for error in ('timeout','cancelled'):
            with self.subTest(error=error):
                result=self.execute(Peer([FINAL,*overflow,Failure(error,'fixture')]))
                self.assertTrue(result['completed'])
                self.assertTrue(result['is_error'])
                self.assertEqual(result['error']['code'],error)
                self.assertEqual(result.get('final_event'),FINAL)
                self.assertEqual(result.get('result'),'kept')
    def test_final_survives_malformed_frame_duplicate_and_cleanup_failure(self):
        peers=[Peer([FINAL,b'not-json']),Peer([FINAL,FINAL]),
               Peer([FINAL],finish_error=Failure('timeout','fixture')),
               Peer([FINAL],cleanup_error=Failure('cleanup_unconfirmed','fixture'))]
        for peer in peers:
            with self.subTest(peer=peer):
                result=self.execute(peer)
                self.assertTrue(result['is_error'])
                self.assertEqual(result.get('final_event'),FINAL)
    def test_invalid_final_cannot_claim_success(self):
        invalid=[{'type':'result','is_error':False},
                 dict(FINAL,session_id=None),dict(FINAL,subtype=4),
                 dict(FINAL,subtype='error_max_turns',is_error=False),
                 dict(FINAL,result={'not':'text'})]
        for final in invalid:
            with self.subTest(final=final):
                result=self.execute(Peer([final]))
                self.assertTrue(result['is_error'])
                self.assertEqual(result['error']['code'],'invalid_vendor_response')
    def test_native_failure_and_unknown_fields_are_retained(self):
        final=dict(FINAL,subtype='error_during_execution',is_error=True,
                   errors=['native failure'])
        final.pop('result')
        result=self.execute(Peer([final]))
        self.assertTrue(result['is_error'])
        self.assertEqual(result['final_event'],final)
    def test_cleanup_error_preserves_primary_execution_error(self):
        result=self.execute(Peer([FINAL,Failure('timeout','fixture timeout')],
                                 cleanup_error=Failure('cleanup_unconfirmed','fixture cleanup')))
        self.assertEqual(result['error']['code'],'timeout')
        self.assertEqual(result.get('cleanup_error',{}).get('code'),'cleanup_unconfirmed')
        self.assertEqual(result.get('final_event'),FINAL)

if __name__=='__main__': unittest.main()
