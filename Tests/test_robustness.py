"""Executable regressions; fixtures never contact Anthropic or a model."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parent.parent
FAKE='''#!/usr/bin/env python3
import json,sys
if sys.argv[1:]==["--version"]:
    print("2.1.59 (Claude Code)"); raise SystemExit
prompt=sys.argv[-1]
if prompt.startswith("--") and (len(sys.argv)<2 or sys.argv[-2]!="--"):
    print("prompt was parsed as an option",file=sys.stderr);raise SystemExit(64)
print(json.dumps({"type":"result","subtype":"error_max_turns" if prompt=="error" else "success","is_error":prompt=="error","result":"fixture","session_id":"12345678-1234-4234-9234-123456789012"}),flush=True)
'''

class RobustnessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        fake=Path(self.temp.name)/'claude';fake.write_text(FAKE);fake.chmod(0o755)
        self.p=subprocess.Popen([sys.executable,str(ROOT/'bin/claude-mcp-adapter')],cwd=self.temp.name,env=dict(os.environ,CLAUDE_CODE_EXECUTABLE=str(fake)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.addCleanup(self.stop);self.buffer=b'';self.serial=2
        self.request({'id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}}})
        self.send({'method':'notifications/initialized'})
    def stop(self):
        if not self.p.stdin.closed:self.p.stdin.close()
        try:self.p.wait(timeout=3)
        except subprocess.TimeoutExpired:self.p.kill();self.p.wait(timeout=3)
        self.p.stdout.close();self.p.stderr.close()
    def send(self,q):
        self.p.stdin.write((json.dumps(dict(jsonrpc='2.0',**q))+'\n').encode());self.p.stdin.flush()
    def receive(self,seconds=5):
        deadline=time.monotonic()+seconds
        with selectors.DefaultSelector() as selector:
            selector.register(self.p.stdout,selectors.EVENT_READ)
            while b'\n' not in self.buffer:
                remaining=deadline-time.monotonic()
                if remaining<=0 or not selector.select(remaining):self.fail('MCP response timeout')
                chunk=os.read(self.p.stdout.fileno(),65536)
                if not chunk:self.fail('MCP exited before response')
                self.buffer+=chunk
        raw,self.buffer=self.buffer.split(b'\n',1);return json.loads(raw)
    def request(self,q):self.send(q);return self.receive()
    def call(self,args):
        self.serial+=1
        return self.request({'id':self.serial,'method':'tools/call','params':{'name':'claude.run','arguments':args}})
    def test_unknown_arguments_are_rejected(self):
        r=self.call({'prompt':'hello','arbitrary_cwd':'/outside'})
        self.assertTrue(r.get('error') or r['result']['isError'])
    def test_vendor_error_is_a_tool_error(self):
        self.assertTrue(self.call({'prompt':'error'})['result']['isError'])
    def test_boolean_parameters_are_typed(self):
        r=self.call({'prompt':'hello','no_session_persistence':'false'})
        self.assertTrue(r.get('error') or r['result']['isError'])
    def test_leading_hyphen_prompt_is_not_a_flag(self):
        self.assertFalse(self.call({'prompt':'--dangerously-skip-permissions'})['result']['isError'])
    def test_ping_is_supported(self):
        self.assertEqual(self.request({'id':10,'method':'ping'})['result'],{})

if __name__=='__main__':unittest.main()
