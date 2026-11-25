"""Claude print binding for the Host-owned vendor execution channel."""

import base64
import os
import queue
import socket
import threading
import time
import uuid

from plugin_runtime import Failure, LineReader, MAX_FRAME, decoded, encoded, write_bytes


CAPABILITY = 'io.github.computer-mcp/vendor-execution-v1'


class VendorChannel:
    def __init__(self):
        if (os.environ.get('COMPUTER_MCP_HOST_CONTEXT') != CAPABILITY
                or os.environ.get('COMPUTER_MCP_HOST_FD') != '3'):
            raise Failure('host_execution_required', 'Managed Claude requires the Host vendor channel')
        self.socket = socket.socket(fileno=3)
        os.set_inheritable(3, False)
        self.socket.setblocking(False)
        self.reader = LineReader(self.socket)
        self.lock, self.writer = threading.Lock(), threading.Lock()
        self.pending = {}
        self.sequence = 0
        self.closed = threading.Event()
        threading.Thread(target=self._receive, daemon=True).start()
        try:
            if self.call('initialize', capability=CAPABILITY).get('capability') != CAPABILITY:
                raise Failure('host_execution_required', 'Host did not negotiate Claude vendor execution')
        except BaseException:
            self.close()
            raise

    def _receive(self):
        try:
            while not self.closed.is_set():
                try:
                    raw = self.reader.next(time.monotonic() + .1)
                except Failure as error:
                    if error.code == 'timeout':
                        continue
                    raise
                if raw is None:
                    break
                result = decoded(raw)
                with self.lock:
                    pending = self.pending.get(result['id'])
                    if pending is not None:
                        pending.put_nowait(result)
        except (Failure, ValueError, KeyError, TypeError, queue.Full):
            pass
        finally:
            self.closed.set()

    def begin(self, op, deadline, **fields):
        pending = queue.Queue(maxsize=1)
        with self.lock:
            if self.closed.is_set() or len(self.pending) >= 16:
                raise Failure('host_execution_closed', 'Claude vendor channel is unavailable')
            self.sequence += 1
            request = self.sequence
            self.pending[request] = pending
        try:
            data = encoded({'id': request, 'op': op, **fields}) + b'\n'
            if len(data) > MAX_FRAME:
                raise Failure('frame_too_large', 'Claude vendor channel frame exceeds its bound')
            with self.writer:
                try:
                    write_bytes(self.socket.fileno(), data, deadline, self.closed)
                except Failure:
                    self.close()
                    raise
            return request, pending
        except BaseException:
            self.discard(request)
            raise

    def discard(self, request):
        with self.lock:
            self.pending.pop(request, None)

    def wait(self, handle, deadline, *, job=None):
        request, pending = handle
        while not self.closed.is_set():
            if job is not None and job.cancelled.is_set():
                self.discard(request)
                job.check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.discard(request)
                raise Failure('timeout', 'Host vendor operation did not confirm its result')
            try:
                reply = pending.get(timeout=min(.05, remaining))
            except queue.Empty:
                continue
            self.discard(request)
            if 'error' in reply:
                code = reply['error']
                if 'result' not in reply and isinstance(code, str):
                    raise Failure(code, 'Host could not settle the Claude vendor effect')
                raise Failure('invalid_host_reply', 'Host returned an invalid Claude vendor reply')
            if not isinstance(reply.get('result'), dict):
                raise Failure('invalid_host_reply', 'Host returned an invalid Claude vendor result')
            return reply['result']
        self.discard(request)
        raise Failure('host_execution_closed', 'Claude vendor channel closed')

    def call(self, op, *, timeout=10, **fields):
        deadline = time.monotonic() + timeout
        return self.wait(self.begin(op, deadline, **fields), deadline)

    def close(self):
        self.closed.set()
        self.reader.close()
        self.socket.close()


class ManagedClaudeRun:
    """Translate one print invocation. Only the Host starts and retires children."""

    def __init__(self, channel, acquisition, run_id):
        if acquisition is None:
            raise Failure('host_execution_required', 'Host did not correlate the Claude acquisition')
        self.channel = channel
        self.acquisition = acquisition
        self.run_id = run_id
        self.probe = self.workload = None
        self.cursor = 0
        self.output = bytearray()
        self.retired = threading.Event()
        self.retirement = threading.Lock()
        self.cancelled = False

    def _call(self, op, *, call=None, child=None, timeout=10, **fields):
        return self.channel.call(
            op, call=call or self.acquisition, acquisition=self.acquisition,
            child=child, timeout=timeout, **fields)

    def detach(self):
        self._call('detach')

    def bind(self):
        receipt = self._call('bind', session=self.run_id)
        self._bind_receipt(receipt)

    def _bind_receipt(self, receipt):
        def identifier(key):
            value = receipt.get(key)
            try:
                return str(uuid.UUID(value))
            except (ValueError, TypeError, AttributeError):
                raise Failure('invalid_host_reply', 'Host did not identify the Claude child slots') from None
        probe, workload = identifier('probe'), identifier('workload')
        if (probe == workload or self.probe not in (None, probe)
                or self.workload not in (None, workload)):
            raise Failure('invalid_host_reply', 'Host changed the Claude child slot identity')
        self.probe, self.workload = probe, workload

    def launch(self, job, deadline):
        job.check()
        self._observe('probe', deadline, job, child=self.probe)
        job.check()
        # Never replay launch. A missing reply is resolved by exact-child retirement.
        self._observe('launch', deadline, job, child=self.workload)

    def _observe(self, op, deadline, job, *, child, **fields):
        job.check()
        deadline = min(deadline, time.monotonic() + 10)
        handle = self.channel.begin(
            op, deadline, call=self.acquisition, acquisition=self.acquisition,
            child=child, **fields)
        return self.channel.wait(handle, deadline, job=job)

    def read(self, deadline, job):
        while True:
            job.check()
            newline = self.output.find(b'\n')
            if newline >= 0:
                line = bytes(self.output[:newline+1])
                del self.output[:newline+1]
                return line
            reply = self._observe('read', deadline, job, child=self.workload, after=self.cursor)
            if 'data' in reply:
                cursor = reply.get('cursor')
                try:
                    line = base64.b64decode(reply['data'], validate=True)
                except (TypeError, ValueError):
                    raise Failure('invalid_host_reply', 'Host returned invalid Claude output') from None
                if type(cursor) is not int or cursor != self.cursor + 1:
                    raise Failure('invalid_host_reply', 'Host returned an unexpected Claude output cursor')
                if not line:
                    raise Failure('invalid_host_reply', 'Host returned an empty Claude output chunk')
                self.output.extend(line)
                if len(self.output) > MAX_FRAME:
                    raise Failure('frame_too_large', 'Claude emitted an oversized frame')
                self.cursor = cursor
                continue
            if reply.get('eof') is True:
                if self.output:
                    raise Failure('invalid_vendor_response', 'Claude output ended in a partial frame')
                return None
            if reply.get('eof') is not False:
                raise Failure('invalid_host_reply', 'Host did not report Claude output state')
            job.cancelled.wait(min(.01, max(0, deadline - time.monotonic())))

    def finish(self, deadline, job):
        while True:
            receipt = self._observe('receipt', deadline, job, child=self.workload)
            self._bind_receipt(receipt)
            code, signal = receipt.get('exit_code'), receipt.get('exit_signal')
            if type(code) is int and 0 <= code <= 255:
                return code
            if type(signal) is int and 1 <= signal <= 127:
                return 128 + signal
            if receipt.get('workload_settled') is True:
                raise Failure('native_exit_unavailable', 'Host did not report the Claude native exit outcome')
            job.cancelled.wait(min(.05, max(0, deadline - time.monotonic())))

    def cancel(self, call, job):
        # Keep the addressed permission call alive through retirement. The run
        # worker may observe the cancellation before the Host replies.
        with self.retirement:
            self._close(call)
            self.cancelled = True
            job.cancel()

    def control_cancelled(self):
        with self.retirement:
            return self.cancelled

    def close(self):
        with self.retirement:
            self._close()

    def _close(self, call=None):
        if self.retired.is_set():
            return
        try:
            if self.workload is None:
                self._bind_receipt(self._call('receipt'))
            try:
                receipt = self._call('retire', call=call, child=self.workload)
            except Failure as error:
                if call is not None and error.code in ('vendor_effect_denied', 'vendor_effect_stale'):
                    raise
                receipt = self._call('receipt', child=self.workload)
            self._bind_receipt(receipt)
            if not all(receipt.get(key) is True for key in
                       ('retired', 'probe_settled', 'workload_settled')):
                raise Failure('cleanup_unconfirmed', 'Host did not confirm both Claude child receipts')
            self.retired.set()
        except (Failure, OSError) as error:
            if (call is not None and isinstance(error, Failure)
                    and error.code in ('vendor_effect_denied', 'vendor_effect_stale')):
                raise
            raise Failure('cleanup_unconfirmed', 'Host did not confirm Claude child cleanup') from error
