"""Pure metrics: explicit denominators and no inferred model compliance."""
import math


def percentile(values, percent):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * percent / 100
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def summarize(rows):
    latencies = [r['latency_ms'] for r in rows if r.get('latency_ms') is not None]
    return {'attempts': len(rows),
            'success_rate': sum(bool(r.get('success')) for r in rows) / len(rows) if rows else None,
            'latency_samples': len(latencies),
            'latency_p50_ms': percentile(latencies, 50),
            'latency_p95_ms': percentile(latencies, 95)}


def score_trial(trial):
    calls = trial.get('calls', [])
    valid_start = bool(calls) and calls[0]['selection'] == trial['initial']
    after = calls[1:] if valid_start else []
    if trial['condition'] == 'steered':
        after = [c for c in after if c.get('after_guidance') is True]
    target_calls = [c for c in after if c['selection'] == trial['target']
                    and c['value'] == trial['target_value']]
    final = trial.get('final') or {}
    valid = valid_start and not trial.get('error')
    adopted = valid and bool(trial.get('emitted')) and bool(target_calls)
    revised = valid and bool(target_calls) and final == {
        'selection': trial['target'], 'value': trial['target_value']}
    initial = valid and final == {'selection': trial['initial'], 'value': trial['initial_value']}
    return {'valid_initial_call': valid_start, 'adopted': bool(adopted),
            'revised_target_success': bool(revised), 'initial_task_success': bool(initial),
            'wrong_calls_after_boundary': sum(c['selection'] != trial['target'] for c in after),
            'calls_until_target': next((i + 1 for i, c in enumerate(after)
                                       if c['selection'] == trial['target']), None)}
