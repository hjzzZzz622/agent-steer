# Initial skeleton implementation plan

Goal: ship a tested framework-independent core and explicit adapter extension points.
Architecture: immutable messages, replaceable store protocol, one consumer per run.
Stack: Python >=3.9, standard library runtime, setuptools packaging, unittest.
Spec: design.md.

- [x] Write tests for run isolation, FIFO reads, ack/retry, invalid input, wire format,
  concurrent submission, callback failure, and the 0907 -> 0906 scenario.
- [x] Run tests before implementation to confirm missing core behavior.
- [x] Implement src/agent_steer/core and adapters/base.py, then run tests.
- [x] Add three documented adapter namespaces, example, README, MIT and pyproject.
- [x] Build/install locally, run example and tests, inspect tracked files.
- [ ] Create public hjzzZzz622/agent-steer, publish initial commit, verify remote tree.
