#!/usr/bin/env python3
"""Inert native CLI peer for the isolated source consumer, never a model client."""
import json
import os
from pathlib import Path
import sys
import time


def invoke(arguments):
    if arguments == ['--version']:
        print('2.1.59 (Claude Code)')
        return
    assert arguments[-2] == '--'
    prompt = arguments[-1]
    def option(flag):
        for index, value in enumerate(arguments[:-2]):
            if value == flag:
                return arguments[index + 1]
            if value.startswith(flag + '='):
                return value.split('=', 1)[1]
        raise AssertionError('Missing fixture option ' + flag)
    mode = option('--permission-mode')
    assert mode in ('dontAsk', 'plan', 'acceptEdits')
    session = next((value.split('=', 1)[1] for value in arguments
                    if value.startswith(('--resume=', '--session-id='))),
                   '12345678-1234-4234-9234-123456789012')
    with Path('native-calls.jsonl').open('a') as stream:
        stream.write(json.dumps({'prompt': prompt, 'mode': mode, 'session': session,
                                 'argv': arguments}) + '\n')
    output = option('--output-format')
    if output == 'stream-json':
        # Print mode must reach EOF on stdin without an in-band control write.
        assert os.read(0, 1) == b''
    if prompt == 'hold':
        Path('native-ready').write_text(str(os.getpid()))
        while True:
            time.sleep(1)
    if prompt == 'sibling':
        Path('sibling-ready').write_text(str(os.getpid()))
        deadline = time.monotonic() + 30
        while not Path('finish-sibling').exists():
            if time.monotonic() >= deadline:
                raise SystemExit(24)
            time.sleep(.02)
    value = prompt
    if prompt == 'boundaries':
        outside = json.loads(Path('outside.json').read_text())
        denied = []
        for path in outside:
            outcomes = []
            for operation in ('read', 'write'):
                try:
                    if operation == 'read':
                        Path(path).read_bytes()
                    else:
                        with Path(path).open('a') as stream:
                            stream.write('escaped')
                except PermissionError:
                    outcomes.append(operation)
            denied.append(outcomes)
        locations = {key: os.environ[key] for key in
                     ('HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME', 'TMPDIR')}
        for directory in locations.values():
            with (Path(directory) / 'claude-consumer-marker').open('a') as stream:
                stream.write('x')
        Path('selected-write').write_text('worktree')
        value = json.dumps({'cwd': str(Path.cwd()), 'locations': locations, 'denied': denied})
    result = {'type': 'result', 'subtype': 'success', 'is_error': False,
              'result': value, 'session_id': session, 'observed_permission_mode': mode}
    if output == 'stream-json':
        print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': session}), flush=True)
    print(json.dumps(result), flush=True)
    if prompt == 'nonzero-after-final':
        raise SystemExit(23)


if __name__ == '__main__':
    invoke(sys.argv[1:])
