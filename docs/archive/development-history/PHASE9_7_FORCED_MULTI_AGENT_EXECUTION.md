# Phase 9.7 — Forced Multi-Agent Execution

The Agent Runs launcher is an explicit orchestration surface. Clicking **Run with AI Agents** now bypasses ordinary-chat classification and always creates a coordinated run.

## Execution profiles

- **Fast**: 90-second run cap, 35-second specialist cap, 20-second synthesis cap, no timeout retry.
- **Balanced**: 150-second run cap, 60-second specialist cap, 30-second synthesis cap, bounded timeout retry.
- **Deep**: 240-second run cap, 90-second specialist cap, 45-second synthesis cap, bounded timeout retry.

Profiles remain subject to stricter platform limits. Safety, ownership, approval, cancellation, tool allow-lists, and context budgets are unchanged.
