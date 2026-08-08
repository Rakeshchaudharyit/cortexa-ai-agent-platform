# Phase 9.9.x — Multi-Agent Rollback

The multi-agent execution surface is disabled by default after repeated end-to-end stability failures in the request-scoped orchestration path.

## Product baseline

The supported portfolio baseline is now:

- authenticated Chat
- retrieval-augmented generation
- document management
- long-term memory
- tool history
- enterprise admin features unrelated to Agent Runs

## Safety decision

The multi-agent source, migrations, and historical data are preserved for future isolated redesign. The user-facing launcher, navigation links, and automatic multi-agent routing are disabled. `MULTI_AGENT_ENABLED` defaults to `false`.

This avoids deleting valuable research code while preventing unstable orchestration from affecting the portfolio demonstration.

## Re-enabling

Do not re-enable the feature until orchestration runs in a detached worker with its own database-session lifecycle and passes end-to-end persistence, cancellation, reconnect, and terminal-state tests.
