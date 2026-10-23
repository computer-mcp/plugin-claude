#!/usr/bin/env python3
"""Deterministic stream-json peer; no credentials or networking."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

if sys.argv[1:]==['--version']:
    print('unsupported' if os.environ.get('FIXTURE_WRONG_VERSION') else '2.1.59 (Claude Code)')
    raise SystemExit
args=sys.argv[1:]
assert args[-2]=='--'
prompt=args[-1]
mode=args[args.index('--permission-mode')+1]
session=next((a.split('=',1)[1] for a in args if a.startswith('--resume=') or a.startswith('--session-id=')),'12345678-1234-4234-9234-123456789012')
def emit(value):print(json.dumps(value),flush=True)
def result(error=False,value='done'):
    emit({'type':'result','subtype':'error_max_turns' if error else 'success','is_error':error,'result':value,'session_id':session,'observed_permission_mode':mode})
emit({'type':'system','subtype':'init','session_id':session})
if prompt in ('fork','earlychild'):
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
    Path(os.environ['FIXTURE_MARKER']).write_text(json.dumps([os.getpid(),child.pid]))
    if prompt=='earlychild':result();raise SystemExit
    while True:time.sleep(1)
elif prompt=='slow':
    while True:time.sleep(1)
elif prompt=='huge':sys.stdout.write('x'*1048577);sys.stdout.flush();time.sleep(120)
elif prompt=='huge-final':result(value='x'*200000)
elif prompt=='malformed':print('not-json',flush=True)
elif prompt=='missing':pass
elif prompt=='flood':
    for i in range(600):emit({'type':'assistant','message':{'content':[{'type':'text','text':'x'*4096}]}})
    result()
elif prompt=='error':result(True)
elif prompt=='error-exit':result(True);raise SystemExit(2)
elif prompt=='hang-after-final':result();time.sleep(120)
elif prompt=='env':result(value=json.dumps([k for k in os.environ if k.startswith('COMPUTER_MCP_')]))
else:result(value=prompt)
