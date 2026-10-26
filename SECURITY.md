# Security Policy

## Supported versions

This repository is a pre-release sample: fixes land on `master`.

## Reporting a vulnerability

Please **do not** open public issues for exploitable vulnerabilities. Instead:

1. Use GitHub's **private vulnerability reporting** on this repository
   ("Security" → "Report a vulnerability"), or contact the maintainers
   directly.
2. Include: affected endpoint/build, reproduction steps, impact, and — for
   server-side issues — the `X-Request-ID` from the error envelope (it appears
   in server logs).
3. You will get an acknowledgement as soon as practical; please allow a
   reasonable window before any public disclosure.

## Scope & notes

- Security architecture and threat model:
  [docs/SECURITY.md](docs/SECURITY.md) and
  [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).
- Out of scope: denial-of-service against the demo/mock provider, issues
  requiring prior admin/owner access that are already documented as residual
  risks, and heuristic prompt-injection false positives/negatives (documented
  limitation).
- No real provider credentials exist in this repository. Never commit
  `SENTINEL_*_API_KEY` values or a production `SENTINEL_AUTH_SECRET`.
