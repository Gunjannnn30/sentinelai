"""Deterministic first-pass prompt-injection detection.

## What this is

A transparent, configurable detector built from explicit regex/rule patterns.
Every rule has a stable id, a category, a severity, a human-readable
description, and a weight. Rules are reviewed and versioned in code — an
analyst can always see exactly why a request was flagged.

## Categories

- ``instruction_override``  — attempts to override/replace system instructions
- ``secrets_exfiltration``  — attempts to reveal secrets, keys, hidden prompts
- ``hierarchy_manipulation``— role/sys prompt manipulation ("you are DAN", fake system turns)
- ``safety_bypass``         — attempts to bypass configured safety/guardrail policies

## Honest limitations (also in docs/SECURITY.md)

- This is a **risk signal, not proof** of malice. Legitimate security research,
  red-teaming prompts and creative writing will trigger rules → false positives.
- Deterministic patterns cannot catch obfuscation (leetspeak, translations,
  homoglyphs, multi-turn staged attacks, encoding tricks) → false negatives.
- Never treat "no finding" as "safe". Combine with policy review and human audit.
- We make no claim of completeness or of being a substitute for a classifier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class InjectionRule:
    id: str
    category: str
    severity: str          # low | medium | high | critical
    weight: int            # contribution to risk score
    description: str
    pattern: re.Pattern


@dataclass
class InjectionFinding:
    rule_id: str
    category: str
    severity: str
    weight: int
    description: str
    excerpt: str           # matched text, truncated (already potentially masked later)

    def as_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity,
            "weight": self.weight,
            "description": self.description,
            "excerpt": self.excerpt,
        }


@dataclass
class InjectionResult:
    findings: list[InjectionFinding] = field(default_factory=list)
    score: int = 0

    @property
    def flagged(self) -> bool:
        return bool(self.findings)

    @property
    def top_category(self) -> str | None:
        if not self.findings:
            return None
        return max(self.findings, key=lambda f: f.weight).category

    @property
    def max_severity(self) -> str:
        order = ["low", "medium", "high", "critical"]
        if not self.findings:
            return "none"
        return max((f.severity for f in self.findings), key=lambda s: order.index(s))

    def as_dict(self) -> dict:
        return {
            "flagged": self.flagged,
            "score": self.score,
            "max_severity": self.max_severity,
            "categories": sorted({f.category for f in self.findings}),
            "findings": [f.as_dict() for f in self.findings],
        }


def _r(id_: str, category: str, severity: str, weight: int, description: str, pattern: str,
       flags: int = re.IGNORECASE) -> InjectionRule:
    return InjectionRule(id_, category, severity, weight, description, re.compile(pattern, flags))


RULES: list[InjectionRule] = [
    # ── instruction override ────────────────────────────────────────────────
    _r("inj-001", "instruction_override", "high", 40,
       "Explicit instruction to ignore or discard prior/system instructions",
       r"\b(ignore|disregard|forget|override)\b[^.?!]{0,80}\b(previous|prior|above|earlier|system|"
       r"all|any|your)\b[^.?!]{0,60}\b(instructions?|prompts?|rules?|guidelines?|directives?)\b"),
    _r("inj-002", "instruction_override", "high", 40,
       "Instruction to replace the system prompt",
       r"\b(new|replacement|updated)\s+system\s+prompt\b|\bsystem\s+prompt\s*(is|now|=)\b"),
    _r("inj-003", "instruction_override", "medium", 25,
       "Attempts to redefine the assistant's instructions mid-conversation",
       r"\bfrom\s+now\s+on\b[^.?!]{0,60}\b(act|behave|respond|answer|follow)\b"
       r"[^.?!]{0,60}\b(different|otherwise|new rules?)\b"),
    # ── secrets exfiltration ────────────────────────────────────────────────
    _r("inj-010", "secrets_exfiltration", "critical", 50,
       "Request to reveal the hidden/system prompt",
       r"\b(reveal|show|print|output|repeat|display|leak|expose)\b[^.?!]{0,60}\b(hidden|"
       r"system|original|initial|secret)\s+(prompt|instruction)s?\b"),
    _r("inj-011", "secrets_exfiltration", "critical", 50,
       "Request to expose credentials, keys or internal configuration",
       r"\b(show|reveal|leak|output|print|give|tell)\b[^.?!]{0,40}\b(api\s*keys?|access\s*keys?|"
       r"secrets?|credentials?|tokens?|passwords?|env(ironment)?\s*variables?|internal\s+config)\b"),
    _r("inj-012", "secrets_exfiltration", "high", 35,
       "Prompt asks the model to act as a prompt-echo / extractor",
       r"\bas\s+an?\s+(unrestricted|unfiltered|jailbroken)\b|\bDAN\s+mode\b|"
       r"\bstart\s+your\s+response\s+with\s+['\"]?(sure|here)"),
    # ── hierarchy manipulation ──────────────────────────────────────────────
    _r("inj-020", "hierarchy_manipulation", "high", 40,
       "Fake system/developer role injection",
       r"^\s*\[?\s*(system|developer)\s*\]?\s*:"),  # multiline evaluated separately
    _r("inj-021", "hierarchy_manipulation", "high", 40,
       "Claims a new developer/system message overriding safety",
       r"\b(developer|system)\s+message\s*[:\-]\s*|\bpretend\s+(there\s+is\s+)?no\s+system\s+prompt\b"),
    _r("inj-022", "hierarchy_manipulation", "medium", 25,
       "Role-play framing used to shed constraints",
       r"\broleplay\s+as\b[^.?!]{0,60}\b(without|no|free)\s+(restrictions?|limits?|rules?)\b|"
       r"\b(in\s+a\s+fictional\s+world|hypothetically)\s+where\s+(you|there)\s+(must|have\s+no)\b"),
    _r("inj-023", "hierarchy_manipulation", "medium", 25,
       "Role-claim jailbreak ('you are DAN') or demand for unconditional obedience",
       r"\byou\s+(are|will\s+be)\s+(now\s+)?DAN\b|"
       r"\bmust\s+(now\s+)?(obey|comply\s+with|follow)\s+(any|every|all)\s+"
       r"(request|instruction|command)s?\b"),
    # ── safety bypass ───────────────────────────────────────────────────────
    _r("inj-030", "safety_bypass", "critical", 50,
       "Direct request to disable/bypass safety or policy checks",
       r"\b(disable|turn\s+off|bypass|remove|circumvent|skip)\b[^.?!]{0,60}\b(safety|guardrails?|"
       r"content\s+polic|filters?|restrictions?|moderation|checks?)s?\b"),
    _r("inj-031", "safety_bypass", "high", 40,
       "Instruction to keep the request secret from reviewers/auditors",
       r"\b(do\s+not\s+(tell|inform|mention)|never\s+(tell|mention|reveal)|keep\s+(this\s+)?"
       r"(secret|quiet|hidden))\b[^.?!]{0,60}\b(user|human|reviewer|auditor|anyone)\b"),
    _r("inj-032", "safety_bypass", "medium", 25,
       "Instruction to output a specific forbidden token/format to prove override",
       r"\bif\s+you\s+can\s+(say|output|print)\b\s*[\"']?\s*( Dan | DAN | PWNED | pwned )"),
    _r("inj-033", "safety_bypass", "medium", 25,
       "Encoding/obfuscation hint to evade content checks",
       r"\b(encode|obfuscate|base64|rot13|reverse)\b[^.?!]{0,50}\b(so\s+(that\s+)?(it|you|we)\s+"
       r"(bypass|evade|pass|avoid))\b|\bevade\s+(the\s+)?(filters?|detection|checks)\b"),
]

# Rules using ^ need per-line matching; handled by scanning each line.
_LINE_ANCHORED_IDS = {"inj-020"}

DEFAULT_SCORE_THRESHOLD = 40   # findings are reported regardless; used by policies


@dataclass
class InjectionConfig:
    threshold: int = DEFAULT_SCORE_THRESHOLD
    disabled_rules: set[str] = field(default_factory=set)
    extra_patterns: list[tuple[str, str, str, int]] = field(default_factory=list)
    # extra: (rule_id, category, pattern, weight)


def detect_injection(text: str, config: InjectionConfig | None = None) -> InjectionResult:
    """Scan ``text`` and return all rule matches plus a weighted risk score."""
    cfg = config or InjectionConfig()
    findings: list[InjectionFinding] = []
    if not text:
        return InjectionResult(findings=[], score=0)

    lines = text.splitlines() or [text]
    for rule in RULES:
        if rule.id in cfg.disabled_rules:
            continue
        if rule.id in _LINE_ANCHORED_IDS:
            matched = next((ln for ln in lines if rule.pattern.search(ln)), None)
        else:
            m = rule.pattern.search(text)
            matched = m.group(0) if m else None
        if matched:
            findings.append(
                InjectionFinding(
                    rule_id=rule.id,
                    category=rule.category,
                    severity=rule.severity,
                    weight=rule.weight,
                    description=rule.description,
                    excerpt=matched.strip()[:200],
                )
            )

    for rule_id, category, pattern, weight in cfg.extra_patterns:
        try:
            m = re.compile(pattern, re.IGNORECASE | re.MULTILINE).search(text)
        except re.error:
            continue
        if m:
            findings.append(
                InjectionFinding(
                    rule_id=rule_id, category=category, severity="high",
                    weight=weight, description="Custom configured rule",
                    excerpt=m.group(0)[:200],
                )
            )

    score = min(100, sum(f.weight for f in findings))
    return InjectionResult(findings=findings, score=score)
