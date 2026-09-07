# Benchmark design and plan

Deliverable: dependency-free repository benchmark module. Offline transport runs real
CLI subprocesses and production SQLite/hooks. Live mode launches the user's Claude
CLI in isolated workspaces, with fixed date/region/source tasks and two conditions.

A deterministic query fixture records executed selections and returns fixed values.
A benchmark hook observes the first completed fixture call, injects a correction
once for the steered condition, then calls the unmodified production hook handler.
Injection is at a tool boundary, not a test of preemption or arbitrary timing.
Scoring checks fixture calls plus final structured result, not verbal acceptance.
The fixture and trace are trusted instrumentation, not adversarial tamper-proofing.

No-steering runs lack revised-target information. Report initial-task completion
separately from revised-target completion, and do not claim equal-information causal
superiority. Preserve all attempted trials, timeouts and malformed model outputs.
Unknown costs/usage remain null. Exclude missing latencies from percentiles but
report denominator. Require explicit model and per-trial budget in live mode.

- [ ] Write scorer tests for wrong/missing calls, malformed outputs and empty samples.
- [ ] Implement scenarios, metrics, subprocess transport and live trial harness.
- [ ] Add real-hook fixture tests, CLI validation and output artifacts.
- [ ] Run offline benchmark, unit tests, independent review; document limitations.
- [ ] Publish and verify remote changes. Live model results require Claude CLI.
