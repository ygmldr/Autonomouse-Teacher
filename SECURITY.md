# Security policy

## Scope and non-goals

This repository is an offline-first M0 verification facility, not a production
service. All committed M0 runs use **0 real API keys**, **no external network**,
and the LiveGate is **not unlocked**; real Live/provider/billing paths remain
BLOCKED. Do not treat repository tests, fixtures or the fake provider as a
credential-handling production system.

## Secrets and credentials

Never commit real API keys, credentials, tokens, passwords, private keys, `.env`
files or machine credentials. In particular:

- Do not commit `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, cloud
  access keys, GitHub/Slack tokens, database URLs with passwords, JWTs, or
  private-key files.
- Do not commit `.env`/`.env.*` real values, `id_rsa`/other private-key files,
  `.npmrc`, `.pypirc`, `.netrc`, `git-credentials`, or `*.pem`/`*.p12`/`*.pfx`.
- Test fixtures may use only explicit synthetic sentinels such as
  `sk-FAKE-*`, `sk-fake-*`, `sk-INVENTED-*`, `sk-livefake*`, or `sk-test*`.
  Never substitute a real-shaped token even temporarily.
- `artifacts/` (including the review packet), `.env`, `.env.*` (except the
  example file), local databases and node_modules are intentionally gitignored
  and must not be force-added.

The secret scanner and CI check are defense-in-depth heuristics, not a
guarantee. A clean scan does not authorize a Live run.

## Reporting a security issue

Use GitHub Security Advisories for this repository when available, or open a
minimal Issue. Do **not** paste suspected keys, credentials, exploit tokens or
other sensitive values into an Issue, PR, log or screenshot; report the affected
file/path and a masked description, and coordinate a private channel with the
maintainer. If you discover a real credential that appears committed, do not
copy it; notify the maintainer immediately so it can be revoked and removed
from the working tree.

## Secret scanning

Run locally (standard-library Python, no network):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/security/scan_git_secrets.py
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/security/scan_git_secrets.py --self-test
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/security/scan_git_secrets.py --no-history
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/security/scan_git_secrets.py --json
```

The default scan covers tracked files, all historical blobs reachable from all
refs, and all commit messages. Findings are printed as file/line plus a masked
representation only and exit non-zero. The GitHub Actions workflow
`.github/workflows/secret-scan.yml` runs the same full-history scan on every
push and pull request with `fetch-depth: 0`.

This scanner is an additional guard; it does not replace human review, provider
key revocation, GitHub secret scanning, or a private vulnerability-reporting
channel.
