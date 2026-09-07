"""Run with python -m benchmarks.run from a checkout; see benchmarks/README.md."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import random
import shlex
import shutil
import signal
import subprocess
import sys
import time
from uuid import uuid4

from agent_steer.core.sqlite import SQLiteSteeringQueue
from agent_steer.adapters.claude_code.hook import settings
from .metrics import summarize, score_trial
from .scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[1]


def environment():
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT / 'src'), str(ROOT)])
    return env


def hook(db, session):
    start = time.perf_counter()
    result = subprocess.run([sys.executable, '-m', 'agent_steer', '--db', str(db), 'claude-hook'],
                            input=json.dumps({'session_id': session, 'cwd': str(db.parent),
                                              'hook_event_name': 'PostToolUse'}),
                            text=True, capture_output=True, timeout=15, env=environment())
    return result, (time.perf_counter() - start) * 1000


def transport_trial(folder, workers, index):
    db = folder / 'inbox.sqlite3'
    queue = SQLiteSteeringQueue(db)
    session = str(uuid4())
    message = queue.submit(session, '0907 尚未落库，请改查 0906')
    start = time.perf_counter()
    row = {'mode': 'transport', 'trial': index, 'success': False, 'latency_ms': None,
           'deliveries': 0, 'duplicates': 0, 'misdeliveries': 0, 'error': None}
    try:
        wrong, _ = hook(db, str(uuid4()))
        row['misdeliveries'] = int(bool(wrong.stdout.strip()))
        if wrong.returncode:
            raise RuntimeError(wrong.stderr)
        start = time.perf_counter()  # dispatch-to-completed-hook, excludes isolation probe
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outputs = list(pool.map(lambda _: hook(db, session), range(workers)))
        latencies = []
        for result, latency in outputs:
            if result.returncode:
                raise RuntimeError(result.stderr)
            if result.stdout:
                payload = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
                if message.id in payload:
                    row['deliveries'] += 1
                    latencies.append(latency)
                else:
                    row['misdeliveries'] += 1
        row['latency_ms'] = min(latencies) if latencies else None
        row['duplicates'] = max(0, row['deliveries'] - 1)
        row['success'] = row['deliveries'] == 1 and not row['misdeliveries']
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, RuntimeError) as exc:
        row['error'] = str(exc)
    row['elapsed_ms'] = (time.perf_counter() - start) * 1000
    return row


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def run_live_process(command, workspace, timeout):
    process = subprocess.Popen(command, cwd=workspace, env=environment(), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        (workspace.parent / 'stdout.json').write_text(stdout)
        (workspace.parent / 'stderr.txt').write_text(stderr)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def live_trial(folder, scenario, condition, args):
    workspace = folder / 'workspace'
    workspace.mkdir()
    session = str(uuid4())
    config = dict(scenario, session=session, condition=condition,
                  db=str(folder / 'inbox.sqlite3'), trace=str(folder / 'queries.jsonl'),
                  boundary=str(folder / 'boundary'), emissions=str(folder / 'emissions.jsonl'))
    config_path = folder / 'config.json'
    config_path.write_text(json.dumps(config))
    fixture_path = folder / 'fixture.json'
    fixture_path.write_text(json.dumps({'values': {scenario['initial']: scenario['initial_value'],
                                                  scenario['target']: scenario['target_value']},
                                      'trace': config['trace'], 'emissions': config['emissions']}))
    hooks = settings(config['db'])
    for entries in hooks['hooks'].values():
        entries[0]['hooks'][0]['command'] = shlex.join(
            [sys.executable, '-m', 'benchmarks.live_hook', str(config_path)])
    settings_path = folder / 'settings.json'
    settings_path.write_text(json.dumps(hooks))
    query = shlex.join([sys.executable, str(ROOT / 'benchmarks/query.py'), '--fixture', str(fixture_path)])
    prompt = (f'Run this exact query first: {query} {scenario["initial"]}. '
              'Use sequential Bash calls only. After its result, incorporate any runtime guidance '
              'by calling the same query command with the corrected selection. Do not inspect or '
              'modify fixture, configuration or trace files. Preserve task progress. '
              'End with only a JSON object {"selection": "queried selection", "value": returned number}.')
    command = [args.claude_bin, '-p', prompt, '--model', args.model, '--session-id', session,
               '--settings', str(settings_path), '--setting-sources', '',
               '--tools', 'Bash', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--allowedTools', f'Bash({query} *)',
               '--max-turns', '8', '--max-budget-usd', str(args.budget_usd), '--output-format', 'json']
    row = dict(scenario, mode='claude', condition=condition, session=session, calls=[],
               emitted=False, final=None, error=None, cost_usd=None, usage=None)
    start = time.perf_counter()
    try:
        result = run_live_process(command, workspace, args.timeout)
        (folder / 'stdout.json').write_text(result.stdout)
        (folder / 'stderr.txt').write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f'Claude exited {result.returncode}: {result.stderr[:500]}')
        output = json.loads(result.stdout)
        row['cost_usd'] = output.get('total_cost_usd')
        row['usage'] = output.get('usage')
        if output.get('is_error'):
            raise RuntimeError(str(output.get('result', output.get('subtype'))))
        row['final'] = json.loads(output['result'])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, RuntimeError) as exc:
        row['error'] = str(exc)
    row['elapsed_ms'] = (time.perf_counter() - start) * 1000
    row['calls'] = read_lines(Path(config['trace']))
    emissions = read_lines(Path(config['emissions']))
    row['emitted'] = bool(emissions)
    row['emission_at_ns'] = emissions[0]['at_ns'] if emissions else None
    row.update(score_trial(row))
    row['success'] = row['revised_target_success'] if condition == 'steered' else row['initial_task_success']
    # No live latency claim: receipt and model ingestion are different events.
    row['latency_ms'] = None
    return row


def report(rows, output, metadata):
    groups = {}
    for row in rows:
        key = row['mode'] if row['mode'] == 'transport' else row['name'] + '/' + row['condition']
        groups.setdefault(key, []).append(row)
    summary = {'metadata': metadata, 'groups': {key: summarize(value) for key, value in groups.items()}}
    for key, value in groups.items():
        group = summary['groups'][key]
        if value[0]['mode'] == 'transport':
            group.update(duplicates=sum(r['duplicates'] for r in value),
                         misdeliveries=sum(r['misdeliveries'] for r in value),
                         missing_delivery_trials=sum(r['deliveries'] == 0 for r in value))
        else:
            group.update(adoption_rate=sum(r['adopted'] for r in value) / len(value),
                         revised_target_success_rate=sum(r['revised_target_success'] for r in value) / len(value),
                         initial_task_success_rate=sum(r['initial_task_success'] for r in value) / len(value),
                         errors=sum(r['error'] is not None for r in value),
                         cost_samples=sum(r['cost_usd'] is not None for r in value),
                         observed_cost_usd=sum(r['cost_usd'] or 0 for r in value))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    lines = ['# Benchmark report', '', 'Mode: ' + metadata['mode'], '',
             '| Group | Attempts | Success rate | Latency samples | P50 ms | P95 ms |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for key, value in summary['groups'].items():
        lines.append('| ' + ' | '.join(str(x) for x in [key, value['attempts'], value['success_rate'],
                     value['latency_samples'], value['latency_p50_ms'], value['latency_p95_ms']]) + ' |')
    lines += ['', 'Full metrics: summary.json. Every attempted trial: trials.jsonl.',
              'Transport success is not model adoption. Live baseline success uses the initial goal;',
              'steered success uses the revised goal. Compare revised-target rates only with the',
              'explicit caveat that baseline did not receive the new information.',
              'Missing latency/cost is unknown, not zero. Small samples are exploratory.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('transport', 'claude'), default='transport')
    parser.add_argument('--repeats', type=int, default=10)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--output', required=True)
    parser.add_argument('--model')
    parser.add_argument('--budget-usd', type=float)
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--claude-bin', default='claude')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)
    if args.repeats < 1 or not 1 <= args.workers <= 32 or args.timeout <= 0:
        parser.error('repeats/timeout must be positive; workers must be 1..32')
    if args.mode == 'claude':
        if not args.model or args.budget_usd is None or args.budget_usd <= 0:
            parser.error('live mode requires --model and positive --budget-usd per trial')
        if not shutil.which(args.claude_bin):
            parser.error('Claude executable unavailable; no live trials run')
    output = Path(args.output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    metadata = {'mode': args.mode, 'python': platform.python_version(), 'platform': platform.platform(),
                'repeats': args.repeats, 'workers': args.workers, 'seed': args.seed,
                'model': args.model, 'budget_usd_per_trial': args.budget_usd,
                'claude_version': None, 'timeout_seconds': args.timeout,
                'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    if args.mode == 'claude':
        metadata['claude_version'] = subprocess.check_output([args.claude_bin, '--version'], text=True, timeout=15).strip()
    jobs = [(None, None)] * args.repeats if args.mode == 'transport' else [
        (scenario, condition) for scenario in SCENARIOS for condition in ('baseline', 'steered')
        for _ in range(args.repeats)]
    random.Random(args.seed).shuffle(jobs)
    rows = []
    for index, (scenario, condition) in enumerate(jobs):
        folder = output / f'trial-{index:04d}'
        folder.mkdir()
        row = transport_trial(folder, args.workers, index) if args.mode == 'transport' else live_trial(folder, scenario, condition, args)
        row['trial'] = index
        rows.append(row)
        with (output / 'trials.jsonl').open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        report(rows, output, metadata)  # retain partial summary if later interrupted
        print(f'{index + 1}/{len(jobs)} success={row["success"]}', flush=True)
    return 0 if all(r['success'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
