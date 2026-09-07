# Quantitative benchmarks

These benchmarks separate transport correctness from model behavior.

## Reproduce transport results

From the repository root:

```bash
PYTHONPATH=src:. python -m benchmarks.run \
  --mode transport --repeats 20 --workers 4 \
  --output work/benchmark-transport-20
```

Each trial creates a fresh SQLite inbox, submits one message, probes an unrelated
session, then races four real subprocess Hook invocations. The report measures
successful single delivery, duplicates, wrong-session delivery, and Hook latency.
`trials.jsonl` is the source of truth; `summary.json` and `report.md` are derived
artifacts. The benchmark exits nonzero if a trial fails.

## Run Claude behavior benchmark

The live runner requires a locally installed and authenticated Claude CLI. It uses
three deterministic fixture scenarios (date, region and source), each with a
baseline and a steered condition. The baseline receives no revised target; it
measures the initial task. The steered condition injects the revised target after
the first fixture query. Actual tool calls and final structured output are scored.

```bash
PYTHONPATH=src:. python -m benchmarks.run \
  --mode claude --model sonnet --budget-usd 0.25 --timeout 180 \
  --repeats 10 --output work/benchmark-claude-sonnet
```

The command records `claude --version`, model, budget, commit, every prompt trial,
stdout/stderr, tool trace, emission receipt, usage (when Claude reports it), and
cost (when reported). It fails before creating output if the executable, model, or
budget is missing. Use a fresh output directory for every run.

Metrics:

- `initial_task_success`: final output matches the original target and value.
- `adopted`: a target query happened after runtime guidance was emitted.
- `revised_target_success`: target query and final output both match the revised goal.
- `wrong_calls_after_boundary`: calls after the guidance boundary that use another selection.
- transport P50/P95 latency excludes missing samples; missing is reported as unknown.

A successful Hook response only proves that synchronous `additionalContext` was
returned. A model saying “I understand” is not a score. The evaluator requires the
actual fixture query and final JSON. Baseline and steered revised-target rates are
not an equal-information causal experiment; baseline never receives the new target.
Report the distinction, all failed trials, and costs. The fixture is local and
trusted instrumentation, not a security boundary. The live runner has not been run
in this development environment because Claude CLI is unavailable.

## Extending scenarios

Add an entry to `benchmarks/scenarios.py` with `name`, `initial`, `target`,
`initial_value`, `target_value`, and `guidance`. Do not score free-form language;
add a deterministic fixture and assert on observed tool arguments/results. Keep
conditions and prompts identical except for the steering message. Pin model,
CLI version, budget, timeout and seed in reports.
