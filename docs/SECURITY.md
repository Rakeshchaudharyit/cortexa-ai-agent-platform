# Security

Cortexa AI Agent Platform — security philosophy and controls (design contract for all phases).

Cortexa is **local-first**. Security prioritizes preventing accidental data exfiltration, unsafe tool execution, and secret leakage while remaining practical for single-operator and small-team local deployments.

---

## Local-First Execution

- Default inference, embeddings, and speech run on local runtimes (Ollama and local engines).
- Network egress for AI features is not required for the core happy path.
- Any future non-local provider must be:
  - Explicitly configured
  - Isolated behind the provider layer
  - Documented as an opt-in risk

---

## No Hidden Cloud APIs

- Application code must not embed undeclared SaaS AI calls.
- Dependency choices should prefer libraries that do not phone home by default.
- CI and runtime configs must not silently inject third-party AI keys.
- Documentation and UI must not imply cloud backends when the operator is in local mode.

---

## Secret Management

| Practice | Requirement |
| --- | --- |
| Repository | No live secrets; `.env` is gitignored |
| Templates | `.env.example` contains placeholders only |
| Runtime | Secrets via environment or local secret files outside VCS |
| Rotation | Operators can rotate DB/Redis/app secrets without code changes |
| Scope | Least privilege per service container |

Never commit API keys, private certificates, model license keys, or dump files containing PII.

---

## Prompt Injection Mitigation

Agents that read retrieved documents, memory, or tool outputs must treat that content as **untrusted**.

Controls (introduced in relevant phases):

- System instructions separated from user/tool/document content
- Untrusted content clearly delimited in prompts
- Tool allowlists independent of model suggestions
- Refusal paths when retrieval asks the model to ignore policy
- Logging of suspicious patterns where feasible without storing raw secrets

Prompt injection cannot be solved perfectly; defense-in-depth and permission boundaries are mandatory.

---

## Tool Permissions

- Tools are denied by default until registered and granted.
- High-risk tools (filesystem write, network, subprocess) require explicit operator enablement.
- Arguments are schema-validated before execution.
- Execution is timed out and resource-limited.
- Outcomes are audited.

The model proposes; the platform disposes.

---

## Audit Logging

Sensitive actions should emit structured audit events, including at minimum:

- Timestamp (UTC)
- Actor / session identifier
- Action type
- Resource identifiers (not raw secrets)
- Outcome (success / deny / error class)

Audit logs are local by default and retained per operator policy. They support incident review for tool misuse, auth failures, and configuration changes.

---

## Memory Privacy

- Memory is scoped to the appropriate session/user boundary modeled by the application.
- Retention and deletion APIs/policies are first-class (Phase 7+).
- Memory contents are not used to train external models.
- Exports, if offered, are explicit operator actions.

---

## Upload Validation

All uploads (documents, audio, images) must be validated before processing:

- Size limits
- MIME / content-type checks
- Extension allowlists aligned with parsers
- Malformed file rejection
- Quarantine or discard on parser failure
- No executable deployment from upload paths

---

## Safe Execution

| Area | Baseline expectation |
| --- | --- |
| Containers | Non-root where practical; read-only root FS considered in hardening phases |
| Postgres / Redis | Strong local passwords in real `.env`; defaults only for empty local templates |
| Admin surfaces | Not exposed to public internet without additional hardening |
| Dependencies | Pin versions in implementing phases; review high-risk packages |
| Errors | No stack traces or secrets in client-facing responses |

---

## Threat Model Snapshot (Local Deploy)

| Threat | Mitigation direction |
| --- | --- |
| Secret committed to git | `.gitignore`, reviews, secret scanning habits |
| Model exfiltrates data via tools | Tool allowlists, argument validation, audits |
| Malicious document injection | Upload validation + untrusted context handling |
| Ollama / DB exposed broadly | Bind to localhost / Docker network; no public publish by default |
| Supply chain | Lockfiles in later phases; minimal dependency surface |

---

## Phase 0 Security Posture

Phase 0 ships **policy and contracts only**:

- Empty/placeholder env template
- Compose without production secrets
- Documentation of controls for later enforcement

Absence of runtime enforcement in Phase 0 is intentional — not a claim that the running system is already hardened.
