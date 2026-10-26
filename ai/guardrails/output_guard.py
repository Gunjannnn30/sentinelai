"""Output security checks applied to model responses before they reach the caller.

Detects: residual PII (e.g. an identifier the prompt masked but the model
regurgitated), configured prohibited-content patterns, and accidental
disclosure of masked tokens.

**Honest scope**: pattern + keyword heuristics. This is *not* a comprehensive
safety classifier and must not be described as one. It catches predictable
leakage, not adversarial or novel harmful content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ai.guardrails.pii import PiiConfig, mask_pii


@dataclass
class OutputFinding:
    kind: str            # pii | prohibited | masked_token_leak
    severity: str
    detail: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "severity": self.severity, "detail": self.detail}


@dataclass
class OutputCheckResult:
    text: str
    findings: list[OutputFinding] = field(default_factory=list)
    masked: bool = False

    @property
    def action(self) -> str:
        """Suggested action: block if any high-severity finding, else mask/warn."""
        if any(f.severity in ("high", "critical") for f in self.findings):
            return "block"
        if self.findings:
            return "mask" if self.masked else "warn"
        return "allow"

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "masked": self.masked,
            "findings": [f.as_dict() for f in self.findings],
        }


_MASKED_TOKEN_RE = re.compile(r"\[(?:EMAIL|PHONE|API_KEY|JWT|CREDIT_CARD|SSN|NINO|CN_ID)_\d+\]")


def check_output(
    text: str,
    *,
    prohibited_patterns: list[str] | None = None,
    pii_config: PiiConfig | None = None,
    mask_pii_in_output: bool = True,
    masked_tokens_seen: list[str] | None = None,
) -> OutputCheckResult:
    """Inspect a model response. Returns possibly-masked text + findings."""
    findings: list[OutputFinding] = []

    # 1) PII in output
    pii = mask_pii(text, pii_config)
    masked = False
    if pii.found:
        # Masking neutralizes the leak, so a masked finding is remediated
        # (medium); only PII that would reach the caller unmasked is high.
        findings.append(
            OutputFinding(
                kind="pii",
                severity="medium" if mask_pii_in_output else "high",
                detail=f"Response contains sensitive data patterns: {', '.join(pii.types)}.",
            )
        )
        if mask_pii_in_output:
            text = pii.text
            masked = True

    # 2) Re-disclosure of identifiers the caller had masked (token echo)
    echoed = set(_MASKED_TOKEN_RE.findall(text or ""))
    if echoed:
        findings.append(
            OutputFinding(
                kind="masked_token_leak", severity="medium",
                detail="Response repeats masked identifier tokens: " + ", ".join(sorted(echoed)[:5]),
            )
        )

    # 3) Prohibited content patterns (admin-configured, regex)
    for pattern in prohibited_patterns or []:
        try:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        except re.error:
            continue  # a bad admin pattern must not break responses
        if m:
            findings.append(
                OutputFinding(
                    kind="prohibited", severity="high",
                    detail=f"Matched prohibited-output pattern: {m.group(0)[:120]!r}",
                )
            )

    return OutputCheckResult(text=text, findings=findings, masked=masked)
