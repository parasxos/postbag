"""Keep malformed worker replies structured over real MCP stdio.

Fixtures replace only the worker entrypoint and use private ledgers and fake doors.
"""
import asyncio
import base64
from contextlib import asynccontextmanager
import json
import sys

import pytest

pytest.importorskip("mcp", reason="MCP wire checks require the optional mcp extra")
try:
    from mcp import Client, StdioServerParameters, stdio_client
except ImportError:
    pytest.skip("MCP wire checks require mcp 2.x", allow_module_level=True)

from test_mcp import SERVER_SCRIPT, THREAD_A, checked, codex_join, meta, wire, wire_text
import postbag
import postbag_mcp

SECRET = 'FIXTURE-WORKER-SENTINEL-NEVER-EXPOSE'


@pytest.mark.parametrize('recovery', [
    {'action': 'join', 'actor': 'caller'},
    {'action': 'join', 'actor': 'recipient', 'bag': 'default', 'name': 'bob', 'vendor': None},
    {'action': 'join', 'actor': [], 'bag': 'default'},
    {'action': 'read', 'actor': 'caller', 'bag': 'default', 'socket': SECRET},
    [SECRET],
])
def test_malformed_recovery_preserves_the_original_refusal(tmp_path, monkeypatch, recovery):
    monkeypatch.setenv('HOME', str(tmp_path))
    error = postbag.Refusal('original refusal; stop and ask the human', recovery=recovery)

    def refused(*args, **kwargs):
        raise error

    monkeypatch.setattr(postbag, 'send', refused)
    value = postbag_mcp.worker({'operation': 'send', 'vendor': 'codex',
                               'arguments': {'bag': 'default', 'to': 'bob', 'body': 'fixture', 'final': False}})
    assert value == {'ok': False, 'error_code': 'refused', 'submission_state': 'not_submitted',
                     'message': str(error), 'data': {}}
    assert SECRET not in json.dumps(value)
    assert not (tmp_path / '.postbag').exists()


def test_unexpected_send_blocking_error_does_not_claim_pre_submission_contention(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    submitted = []

    def interrupted(*args, **kwargs):
        submitted.append('fake native submission')
        raise BlockingIOError('unexpected failure after submission')

    monkeypatch.setattr(postbag, 'send', interrupted)
    value = postbag_mcp.worker({'operation': 'send', 'vendor': 'codex',
                               'arguments': {'bag': 'default', 'to': 'bob', 'body': 'fixture', 'final': False}})
    assert value['ok'] is False and value['error_code'] == 'operation_failed'
    assert value['submission_state'] == 'unknown'
    assert value['message'].endswith('; stop and ask the human')
    assert len(submitted) == 1
    assert not (tmp_path / '.postbag').exists()


def envelope(**changes):
    result = dict(ok=True, error_code=None, submission_state='submitted',
                  message='synthetic worker success', data={})
    result.update(changes)
    return result


def encoded(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=True).encode('ascii') + b'\n'


invalid_cases = [
    ('missing_fields', {'ok': True, 'message': SECRET}),
    ('missing_ok', {'message': SECRET}),
    ('extra_field', envelope(unexpected=SECRET)),
    ('integer_true', envelope(ok=1, data={'sentinel': SECRET})),
    ('integer_false', envelope(ok=0, error_code='refused', data={'sentinel': SECRET})),
    ('error_on_success', envelope(error_code='contradiction', data={'sentinel': SECRET})),
    ('missing_error_on_failure', envelope(ok=False, submission_state='unknown', data={'sentinel': SECRET})),
    ('empty_error_on_failure', envelope(ok=False, error_code='', submission_state='unknown', data={'sentinel': SECRET})),
    ('integer_error_on_failure', envelope(ok=False, error_code=7, submission_state='unknown', data={'sentinel': SECRET})),
    ('integer_message', envelope(message=7, data={'sentinel': SECRET})),
    ('list_data', envelope(data=[SECRET])),
    ('string_data', envelope(data=SECRET)),
    ('unknown_state', envelope(submission_state='queued', data={'sentinel': SECRET})),
    ('success_null_state', envelope(submission_state=None, data={'sentinel': SECRET})),
    ('failure_null_state', envelope(ok=False, error_code='refused', submission_state=None, data={'sentinel': SECRET})),
    ('success_not_submitted', envelope(submission_state='not_submitted', data={'sentinel': SECRET})),
    ('success_unknown', envelope(submission_state='unknown', data={'sentinel': SECRET})),
    ('message_lone_surrogate', envelope(message='bad \ud800 '+SECRET)),
    ('nested_lone_surrogate', envelope(data={'nested': [{'bad': '\udfff', 'sentinel': SECRET}]})),
    ('nan', envelope(data={'number': float('nan'), 'sentinel': SECRET})),
    ('positive_infinity', envelope(data={'number': float('inf'), 'sentinel': SECRET})),
    ('negative_infinity', envelope(data={'number': -float('inf'), 'sentinel': SECRET})),
    ('non_object', [SECRET]),
]
INVALID = [pytest.param(encoded(value), id=name) for name, value in invalid_cases]
INVALID += [
    pytest.param(b'{malformed '+SECRET.encode('ascii')+b'}\n', id='invalid_json'),
    pytest.param(
        ('{"ok":true,"error_code":null,"submission_state":"submitted",'
         '"message":"'+SECRET+'","data":{"nested":'+ '['*1100 + 'null' + ']'*1100 + '}}\n').encode('ascii'),
        id='nested_recursion'),
]


@asynccontextmanager
async def fixture_worker_session(wire, tmp_path, response, operation="send"):
    worker = tmp_path/'fixture-worker.py'
    worker.write_text(
        'import base64,json,sys\n'
        'assert sys.argv[1:] == ["--worker-v2"]\n'
        f'sys.path.insert(0,{str(SERVER_SCRIPT.parent)!r})\n'
        'import postbag_mcp as real\n'
        'request=json.load(sys.stdin)\n'
        f'if request["operation"]=={operation!r}:\n'
        f'    sys.stdout.buffer.write(base64.b64decode({base64.b64encode(response).decode()!r}))\n'
        'else:\n'
        '    sys.stdout.buffer.write(json.dumps(real.worker(request)).encode("ascii")+b"\\n")\n',
        encoding='utf-8')
    launcher = tmp_path/'fixture-server.py'
    launcher.write_text(
        'import sys\n'
        f'sys.path.insert(0,{str(SERVER_SCRIPT.parent)!r})\n'
        'import postbag_mcp as server\n'
        f'server.__file__={str(worker)!r}\n'
        'server.main()\n', encoding='utf-8')
    log = tmp_path/'fixture-server.stderr'
    with log.open('w', encoding='utf-8') as errors:
        async with Client(stdio_client(StdioServerParameters(
            command=sys.executable, args=[str(launcher)], cwd=tmp_path,
            env=wire.environment), errlog=errors), read_timeout_seconds=15) as client:
            yield client, log


@pytest.mark.parametrize('response', INVALID)
def test_invalid_worker_response_keeps_unknown_send_outcome(wire, tmp_path, response):
    wire.seed(codex_join("ada", THREAD_A))
    before = wire.path().read_bytes()
    results = []

    async def exercise():
        async with fixture_worker_session(wire, tmp_path, response) as (client, log):
            try:
                results.append(await client.call_tool('postbag_send', {
                    'to': 'bob', 'body': 'isolated worker protocol probe', 'final': False}, meta=meta()))
            except Exception as error:
                results.append(error)
            # Even a protocol error must leave the server able to answer a read.
            results.append(await client.call_tool('postbag_read', {}))
            results.append(log)
    asyncio.run(exercise())
    bad, subsequent, log = results
    checked(subsequent)
    assert not isinstance(bad, Exception), bad
    assert SECRET not in wire_text(bad)
    assert SECRET not in log.read_text()
    value = checked(bad, ok=False)
    assert value['error_code'] == 'worker_failed'
    assert value['submission_state'] == 'unknown'
    assert value['data'] == {}
    assert wire.path().read_bytes() == before
    assert wire.calls() == []


VALID = [
    pytest.param(envelope(), id='successful_submission'),
    pytest.param(envelope(ok=False, error_code='refused', submission_state='not_submitted'), id='pre_submission_refusal'),
    pytest.param(envelope(ok=False, error_code='submission_unknown', submission_state='unknown'), id='uncertain_submission'),
    pytest.param(envelope(ok=False, error_code='recording_failed', submission_state='submitted'), id='submitted_recording_failure'),
]


@pytest.mark.parametrize('payload', VALID)
def test_valid_worker_outcome_retains_submission_state(wire, tmp_path, payload):
    wire.seed(codex_join("ada", THREAD_A))
    before = wire.path().read_bytes()
    results = []

    async def exercise():
        async with fixture_worker_session(wire, tmp_path, encoded(payload)) as (client, _):
            results.append(await client.call_tool('postbag_send', {
                'to': 'bob', 'body': 'isolated worker protocol probe', 'final': False}, meta=meta()))
            results.append(await client.call_tool('postbag_read', {}))
    asyncio.run(exercise())
    checked(results[1])
    assert checked(results[0], ok=payload['ok']) == payload
    assert wire.path().read_bytes() == before
    assert wire.calls() == []


@pytest.mark.parametrize('operation,arguments', [('join', {'name': 'ada'}), ('leave', {})])
def test_invalid_worker_response_keeps_null_non_send_state(wire, tmp_path, operation, arguments):
    wire.seed(codex_join("ada", THREAD_A))
    before = wire.path().read_bytes()
    results = []

    async def exercise():
        response = encoded(envelope(unexpected=SECRET))
        async with fixture_worker_session(wire, tmp_path, response, operation) as (client, log):
            results.append(await client.call_tool(f'postbag_{operation}', arguments, meta=meta()))
            results.append(await client.call_tool('postbag_read', {}))
            results.append(log)
    asyncio.run(exercise())
    bad, subsequent, log = results
    checked(subsequent)
    assert not isinstance(bad, Exception), bad
    assert SECRET not in wire_text(bad)
    assert SECRET not in log.read_text()
    value = checked(bad, ok=False)
    assert value['error_code'] == 'worker_failed'
    assert value['submission_state'] is None
    assert value['data'] == {}
    assert wire.path().read_bytes() == before
    assert wire.calls() == []
