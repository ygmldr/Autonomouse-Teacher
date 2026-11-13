# Security approvals — PENDING HUMAN REVIEW

**Status: BLOCKED / NOT APPROVED. No maintainer approval has been issued here.**

This Agent-authored Markdown is an audit template, NOT an authorization token,
credential, approval API or instructions to inject a key. Editing it, setting
an environment variable, matching a Git SHA, passing `--live`, or passing logical
unit tests cannot enable Live. `LiveGate.require_live()` always rejects because
an independently protected human authorization boundary is not deployed.
No real key/environment file was read and no model request was executed.

## Current evidence and limitations

- Offline code is unreviewed, including controller, Adapter, plugin and tests.
- Real Podman local-rootfs negative probes exist; see the threat model and local
  gitignored artifacts. They are partial E5-Full evidence, NOT Live approval.
- E5-P01/P02 hash-change behavior can be logically tested, but complete inventory
  and deployed content still require independent verification.
- **E5-P03 remains BLOCKED**: there is no independently administered launcher,
  credential broker, immutable baseline or OS-enforced protection from this Agent.
- Actual merged DSH registry/disabled dangerous Shell, file execution/network
  tools and session-log upload have not been verified in a reviewed deployment.
- Unit tests with temporary Markdown/environment variables demonstrate local
  fail-closed behavior only; they are not an OS security/independent-human proof.

## Submission template (not yet filled or approved)

| Required field | Current state |
|---|---|
| Human maintainer identity / review date | PENDING |
| Full reviewed Git SHA | PENDING |
| Full diff and independently complete file inventory | PENDING |
| Inventory SHA-256 / configuration SHA-256 | PENDING |
| Dependency locks and artifact digests | PENDING REVIEW |
| Frozen Python controller / Adapter / plugin versions | PENDING REVIEW |
| Exact allowed commands, route and budget constraints | PENDING |
| Actual merged DSH Profile / tool registry evidence | PENDING |
| Dangerous execution tools absent; upload disabled | NOT VERIFIED |
| Independent credential-injection session / protected broker | NOT DEPLOYED |
| Key scope, supplier-side cap and revocation plan | PENDING HUMAN ACTION |
| OS deployment identity and least-privilege policy | PENDING |
| Effective scope / expiry | NONE |

## Required human-controlled deployment (future work, not automatic)

A maintainer must independently inspect the exact immutable code/configuration/
dependency inventory and actual runtime tools, verify hashes outside the Agent's
write authority, and install a separately protected execution/credential boundary.
The controller must never import/exec dynamic candidates or inherit arbitrary
Shell/plugin execution authority. No key may enter images, stages, Prompt, Trace,
logs or the candidate environment. Use a dedicated revocable low-budget key with
provider-side caps. A human personally authorizes the reviewed restricted session;
this repository does not implement key injection or expose a Python allow hook.

Any code, dependency, profile, tool list, route, budget/policy or configuration
change invalidates that baseline and requires new independent human review. The
reviewer must not derive trust from a fingerprint computed over an incomplete
Agent-selected file subset. Human audit records may be added later, but never
serve as the machine credential boundary themselves.

**All Live cases remain BLOCKED; overall decision remains DECISION PENDING.**
