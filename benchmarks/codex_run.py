"""Opt-in real Codex App Server trials, sharing the existing scenario/scoring suite."""
import argparse
import json
from pathlib import Path
import platform
import random
import shlex
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from agent_steer.adapters.codex.runner import run_session
from agent_steer.core.sqlite import SQLiteSteeringQueue
from .metrics import score_trial
from .run import ROOT, read_lines, report
from .scenarios import SCENARIOS


def trial(folder, scenario, condition, args, command=None):
    trace = folder / 'queries.jsonl'
    emissions = folder / 'emissions.jsonl'
    fixture = folder / 'fixture.json'
    fixture.write_text(json.dumps({'values': {scenario['initial']: scenario['initial_value'],
                                             scenario['target']: scenario['target_value']},
                                   'trace': str(trace), 'emissions': str(emissions)}))
    query = shlex.join([sys.executable, str(ROOT / 'benchmarks/query.py'), '--fixture', str(fixture)])
    prompt = (f'First run exactly: {query} {scenario["initial"]}. '
              'Use sequential shell tool calls only. After the query, apply any runtime '
              'guidance by querying the corrected selection with the same command. '
              'Do not read or modify the fixture or instrumentation files. '
              'Return only JSON with selection and value from your final query.')
    queue = SQLiteSteeringQueue(folder / 'inbox.sqlite3')
    submitted = []
    receipt = str(uuid4())
    texts = []
    row = dict(scenario, mode='codex', condition=condition, calls=[], emitted=False,
               final=None, error=None, usage=None, cost_usd=None, latency_ms=None)

    def tick(run_id):
        calls = read_lines(trace)
        if (condition == 'steered' and not submitted and calls
                and calls[0]['selection'] == scenario['initial']):
            submitted.append(queue.submit(run_id, scenario['guidance'] +
                f' Include --receipt {receipt} in the corrected query command.').id)

    def sink(event):
        with (folder / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(event) + '\n')
        if event.get('method') == 'steering/accepted':
            row['emitted'] = True
            with emissions.open('a') as stream:
                stream.write(json.dumps(event) + '\n')
        params = event.get('params', {})
        if event.get('method') == 'item/completed' and params.get('item', {}).get('type') == 'agentMessage':
            texts.append(params['item']['text'])
        if event.get('method') == 'thread/tokenUsage/updated':
            row['usage'] = params.get('tokenUsage')

    start = time.perf_counter()
    try:
        result = run_session(queue, prompt, folder, args.model, timeout=args.timeout,
                             codex_bin=args.codex_bin, sandbox='workspace-write', command=command,
                             sink=sink, on_tick=tick, output_schema={
                                 'type': 'object', 'properties': {'selection': {'type': 'string'},
                                  'value': {'type': 'number'}},
                                 'required': ['selection', 'value'], 'additionalProperties': False})
        row['session'] = result['run_id']
        if result['status'] != 'completed':
            raise RuntimeError(str(result.get('error') or result['status']))
        row['final'] = json.loads(texts[-1]) if texts else None
        if row['final'] is None:
            raise ValueError('No final agentMessage received')
    except (OSError, ValueError, KeyError, RuntimeError, EOFError) as exc:
        row['error'] = str(exc)
    row['elapsed_ms'] = (time.perf_counter() - start) * 1000
    row['calls'] = read_lines(trace)
    # The unpredictable token arrives only via steering; successful fixture calls
    # carrying it prove receipt independent of response/notification arrival order.
    for call in row['calls']:
        call['after_guidance'] = call.get('steering_receipt') == receipt
    row.update(score_trial(row))
    row['receipt_wrong_selection_calls'] = row.pop('wrong_calls_after_boundary')
    row['receipt_calls_until_target'] = row.pop('calls_until_target')
    row['success'] = row['revised_target_success'] if condition == 'steered' else row['initial_task_success']
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='explicitly run model-backed trials')
    parser.add_argument('--model', required=True)
    parser.add_argument('--codex-bin', default='codex')
    parser.add_argument('--output', required=True)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)
    if not args.live:
        parser.error('pass --live to run real Codex model calls')
    if args.repeats < 1 or not 0 < args.timeout <= 3600:
        parser.error('positive repeats and timeout in (0, 3600] required')
    if not shutil.which(args.codex_bin):
        parser.error('Codex executable unavailable; no trials run')
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    version = subprocess.check_output([args.codex_bin, '--version'], text=True, timeout=15).strip()
    metadata = {'mode': 'codex', 'model': args.model, 'codex_version': version,
                'python': platform.python_version(), 'repeats': args.repeats, 'seed': args.seed,
                'timeout_seconds': args.timeout, 'cost_cap': None,
                'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    jobs = [(s, c) for s in SCENARIOS for c in ('baseline', 'steered') for _ in range(args.repeats)]
    random.Random(args.seed).shuffle(jobs)
    rows = []
    for index, (scenario, condition) in enumerate(jobs):
        folder = output / f'trial-{index:04d}'
        folder.mkdir()
        row = trial(folder, scenario, condition, args)
        row['trial'] = index
        rows.append(row)
        with (output / 'trials.jsonl').open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        report(rows, output, metadata)
        print(f'{index + 1}/{len(jobs)} success={row["success"]}', flush=True)
    return 0 if all(r['success'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
