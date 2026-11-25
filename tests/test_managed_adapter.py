"""Exercise the packaged Claude adapter against a deterministic private-channel peer."""

import base64
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile

from support import Client, ROOT
from test_package import builder

CAPABILITY = 'io.github.computer-mcp/vendor-execution-v1'
ORIGIN = 'io.github.computer-mcp/work-invocation'
NATIVE_SESSION = '12345678-1234-4234-9234-123456789012'


class HostPeer:
    def __init__(self):
        self.server, self.adapter = socket.socketpair()
        self.requests = []
        self.runs = {}
        self.options = {}
        self.error = None
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        try:
            with self.server.makefile('rb') as incoming:
                for line in incoming:
                    request = json.loads(line)
                    self.requests.append(request)
                    reply = self.respond(request)
                    if reply is not None:
                        self.server.sendall(json.dumps({'id': request['id'], **reply}).encode() + b'\n')
        except (BrokenPipeError, ConnectionResetError):
            pass
        except BaseException as error:
            self.error = error
        finally:
            self.server.close()

    def respond(self, request):
        op = request['op']
        if op == 'initialize':
            return {'result': {'capability': CAPABILITY}}
        acquisition = request['acquisition']
        run = self.runs.setdefault(acquisition, {
            'probe': str(uuid.uuid4()), 'workload': str(uuid.uuid4()),
            'probe_settled': False, 'workload_settled': False, 'retired': False,
        })
        options = self.options.get(acquisition, {})
        if op == 'detach':
            return {'result': {}}
        if op == 'bind':
            run['handle'] = request['session']
        elif op == 'probe':
            assert request['child'] == run['probe']
            run['probe_settled'] = True
        elif op == 'launch':
            assert run['probe_settled'] and request['child'] == run['workload']
            assert not run.get('launched'), 'Launch replay'
            run['launched'] = True
            if options.get('drop_launch'):
                return None
        elif op == 'read':
            assert run.get('launched') and request['child'] == run['workload']
            if run['retired']:
                return {'error': 'vendor_effect_stale'}
            if options.get('hold'):
                return {'result': {'eof': False}}
            after = request['after']
            event = {'type': 'result', 'subtype': 'success', 'is_error': False,
                     'result': options.get('text', 'deterministic final'), 'session_id': NATIVE_SESSION}
            frame = json.dumps(event).encode() + b'\n'
            chunks = [frame[:19], frame[19:]]
            if after < len(chunks) and not run['retired']:
                return {'result': {'cursor': after + 1,
                                   'data': base64.b64encode(chunks[after]).decode()}}
            return {'result': {'eof': True}}
        elif op == 'retire':
            assert request['child'] == run['workload']
            if options.get('denied_call') == request['call']:
                return {'error': 'vendor_effect_denied'}
            if options.get('uncertain'):
                return {'error': 'cleanup_unconfirmed'}
            run.update(retired=True, probe_settled=True, workload_settled=True)
        elif op == 'receipt':
            assert request['child'] in (None, run['workload'])
        else:
            raise AssertionError(request)
        return {'result': {
            **run, 'exit_code': options.get('exit_code', 0) if run.get('launched') else None,
        }}

    def close(self):
        self.adapter.close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            self.server.shutdown(socket.SHUT_RDWR)
            self.thread.join(timeout=2)
        if self.thread.is_alive():
            raise AssertionError('Fixture carrier did not close')
        if self.error is not None:
            raise self.error


class ManagedArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        stage = tempfile.TemporaryDirectory()
        cls.addClassCleanup(stage.cleanup)
        cls.root = Path(stage.name)
        with zipfile.ZipFile(io.BytesIO(builder.package_bytes(ROOT)[0])) as archive:
            archive.extractall(cls.root)
        cls.adapter = cls.root / 'bin/claude-mcp-managed'

    def setUp(self):
        self.home = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def open(self):
        host = HostPeer()
        self.addCleanup(host.close)
        fd = host.adapter.fileno()
        bootstrap = '''
import os, sys
fd = int(sys.argv[1])
os.dup2(fd, 3)
os.set_inheritable(3, True)
if fd != 3:
    os.close(fd)
os.execv(sys.executable, [sys.executable, '-B', *sys.argv[2:]])
'''
        client = Client(self.home, {
            'COMPUTER_MCP_HOST_CONTEXT': CAPABILITY, 'COMPUTER_MCP_HOST_FD': '3',
        }, [sys.executable, '-B', '-c', bootstrap, str(fd), str(self.adapter),
            '--host-vendor-execution'], pass_fds=(fd,))
        self.addCleanup(client.close)
        host.adapter.close()
        self.assertIs(client.initialization['result']['capabilities']['experimental'][CAPABILITY], True)
        return client, host

    def call(self, client, tool, arguments=None, *, origin=None):
        client.serial += 1
        identifier = client.serial
        params = {'name': 'claude.run' + tool, 'arguments': arguments or {}}
        if origin is not None:
            params['_meta'] = {ORIGIN: origin}
        client.send({'jsonrpc': '2.0', 'id': identifier, 'method': 'tools/call', 'params': params})
        return client.wait(identifier)

    def settled(self, client, run):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            result = Client.value(self.call(client, '.result', {'run_id': run}))
            if result['completed']:
                return result
            time.sleep(.02)
        self.fail('Managed Claude run did not settle')

    def test_installed_entrypoint_requires_host_and_public_adapter_stays_standalone(self):
        missing = subprocess.run([sys.executable, '-B', str(self.adapter)],
                                 env={}, capture_output=True, timeout=5)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn(b'Managed Claude requires the Host vendor channel', missing.stderr)
        client = Client(self.home, {}, [
            sys.executable, '-B', str(self.root / 'bin/claude-mcp-adapter')])
        self.addCleanup(client.close)
        self.assertNotIn('experimental', client.initialization['result']['capabilities'])

    def test_preserves_native_exit_and_final_event_when_receipt_is_uncertain(self):
        client, host = self.open()
        origin = str(uuid.uuid4())
        host.options[origin] = {'exit_code': 23, 'uncertain': True}
        reply = self.call(client, '', {'prompt': 'offline print'}, origin=origin)
        self.assertTrue(reply['result']['isError'])
        result = Client.value(reply)
        self.assertEqual(result['exit_code'], 23)
        self.assertEqual(result['session_id'], NATIVE_SESSION)
        self.assertEqual(result['final_event']['result'], 'deterministic final')
        self.assertFalse(result['cleanup_confirmed'])
        self.assertEqual(result['cleanup_error']['code'], 'cleanup_unconfirmed')
        release = Client.value(self.call(client, '.release', {'run_id': result['run_id']}))
        self.assertEqual(release['error']['code'], 'cleanup_unconfirmed')

    def test_addressed_stop_does_not_retire_another_run(self):
        client, host = self.open()
        first, second, stop = (str(uuid.uuid4()) for _ in range(3))
        host.options[first] = {'hold': True}
        host.options[second] = {'hold': True, 'text': 'second run'}
        a = Client.value(self.call(client, '.start', {'prompt': 'first'}, origin=first))
        b = Client.value(self.call(client, '.start', {'prompt': 'second'}, origin=second))
        self.assertNotEqual(a['run_id'], b['run_id'])
        self.assertTrue(Client.value(
            self.call(client, '.cancel', {'run_id': a['run_id']}, origin=stop))['cancel_requested'])
        ended = self.settled(client, a['run_id'])
        self.assertEqual(ended['state'], 'cancelled')
        self.assertTrue(ended['cleanup_confirmed'])
        retirements = [req for req in host.requests if req['op'] == 'retire']
        self.assertEqual([(req['call'], req['acquisition']) for req in retirements], [(stop, first)])
        self.assertFalse(host.runs[second]['retired'])

        runs = Client.value(self.call(client, '.list', {}))['runs']
        self.assertEqual({run['run_id'] for run in runs}, {a['run_id'], b['run_id']})
        cancelled = next(run for run in runs if run['run_id'] == a['run_id'])
        self.assertEqual(cancelled['state'], 'cancelled')
        handle = {'run_id': a['run_id']}
        self.assertIn('events', Client.value(self.call(client, '.events', handle)))
        self.assertTrue(Client.value(self.call(client, '.release', handle))['released'])
        missing = Client.value(self.call(client, '.result', handle))
        self.assertEqual(missing['error']['code'], 'unknown_run')
        self.assertEqual(sum(req['op'] == 'launch' for req in host.requests), 2)

        host.options[second]['hold'] = False
        finished = self.settled(client, b['run_id'])
        self.assertEqual(finished['result'], 'second run')
        self.assertTrue(finished['cleanup_confirmed'])
        self.assertEqual(finished['exit_code'], 0)

    def test_definitively_refused_stop_does_not_cancel_with_original_authority(self):
        client, host = self.open()
        origin, stop = (str(uuid.uuid4()) for _ in range(2))
        host.options[origin] = {'hold': True, 'denied_call': stop}
        run = Client.value(self.call(client, '.start', {'prompt': 'keep running'}, origin=origin))
        handle = {'run_id': run['run_id']}
        denied = Client.value(self.call(client, '.cancel', handle, origin=stop))
        self.assertEqual(denied['error']['code'], 'vendor_effect_denied')
        self.assertFalse(Client.value(self.call(client, '.result', handle))['completed'])
        self.assertFalse(host.runs[origin]['retired'])
        host.options[origin]['hold'] = False
        self.assertTrue(self.settled(client, run['run_id'])['cleanup_confirmed'])

    def test_lost_launch_reply_retires_the_reserved_child_without_replay(self):
        client, host = self.open()
        origin = str(uuid.uuid4())
        host.options[origin] = {'drop_launch': True}
        reply = self.call(client, '', {'prompt': 'one attempt', 'timeout_seconds': 1}, origin=origin)
        result = Client.value(reply)
        self.assertEqual(result['error']['code'], 'timeout')
        self.assertTrue(result['cleanup_confirmed'])
        launches = [r for r in host.requests if r['op'] == 'launch']
        retirements = [r for r in host.requests if r['op'] == 'retire']
        self.assertEqual(len(launches), 1)
        self.assertEqual(len(retirements), 1)
        self.assertEqual(launches[0]['child'], retirements[0]['child'])

    def test_missing_invocation_correlator_has_no_native_effect(self):
        client, host = self.open()
        result = Client.value(self.call(client, '', {'prompt': 'not launched'}))
        self.assertEqual(result['error']['code'], 'host_execution_required')
        self.assertEqual([request['op'] for request in host.requests], ['initialize'])
