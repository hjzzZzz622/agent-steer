# Claude Code MVP design and execution plan

Scope approved: CLI -> durable local inbox -> synchronous Claude Code command hook.
Use SQLite (stdlib), explicit session IDs, SessionStart registration, PostToolUse
and PostToolUseFailure additionalContext output. No SDK dependency or MCP daemon.
Generate a separate settings file for `claude --settings`; never overwrite existing
user settings. macOS/Linux first. Inbox is local trusted-user data, not remote auth.

Emission is not acknowledgement of model compliance. Store emitted state separately;
manual retry resets emission, explicit ack ends core pending state. Serialize hook
emission in a transaction; flush stdout before recording emission. Crash between
stdout and commit can duplicate delivery. After commit but before host ingestion,
manual retry is needed. No exactly-once or preemption guarantee.

- [x] Add subprocess tests for registration, submit, hook JSON, isolation, persistence,
  failures, retry, concurrent hooks, empty/malformed input and generated settings.
- [x] Implement SQLite core, session registry and CLI + Claude hook adapter.
- [x] Document real-agent setup and repeatable 0907/0906 manual acceptance scenario.
- [x] Run tests, build/install wheel, exercise generated command, independent review.
Release procedure: publish this commit and verify the remote file tree.

- [ ] Live Claude model acceptance by the user: Claude CLI is not installed in this
  development environment. See the adapter guide for the exact manual scenario.
