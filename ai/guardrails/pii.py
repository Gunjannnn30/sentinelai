"""PII / secret detection and (by default) irreversible masking.

## Behaviour

- Detection is pattern-based (regex) over the prompt (and optionally output).
- Default transform is **irreversible masking**: ``[EMAIL_1]`` style tokens with
  an index per type, so the same value maps to the same token within one
  request but the original is not recoverable.
- There is *no* reversible mode in this implementation — nothing is encrypted
  or stored that would let anyone reconstruct the original secret from the
  masked text. (Documented in docs/SECURITY.md.)
- Rejected requests never log the unmasked text: masking runs *before* anything
  is written to the log or the database.

## Coverage & honest limits

| Type | Pattern basis | Notes |
|---|---|---|
| email | RFC-ish local@domain | low false-positive rate |
| phone | international / NANP forms | configurable per region |
| api_key | vendor-shaped tokens (sk-, ghp_, AKIA, AIza…) | shape-only, not validity |
| jwt | three base64url segments | shape-only |
| credit_card | Luhn-checked 13–19 digit runs | reduces false positives |
| national_id | generic ``XXXXXX-XXXX`` style, **opt-in per region** | disabled by default |

Regex cannot achieve complete PII recall. Expect misses on unstructured or
novel identifier formats, and occasional masking of non-PII strings that look
like identifiers. This is a data-loss-reduction control, not a guarantee.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Order matters: more specific first so partial overlaps mask correctly.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("api_key", re.compile(
        r"\b(?:sk-[A-Za-z0-9_\-]{16,}|sk-ant-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{16,}|"
        r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|"
        r"xox[baprs]-[A-Za-z0-9\-]{10,}|glpat-[A-Za-z0-9_\-]{16,})\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b")),
    ("phone", re.compile(
        r"(?<!\w)(?:\+\d{1,3}[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?)?\d{3,4}[\s.\-]\d{3,4}"
        r"(?:[\s.\-]\d{2,4})?(?!\w)")),
    ("credit_card", re.compile(r"(?<!\d)(?:\d[ \-]?){12,18}\d(?!\d)")),
]

# Region-specific identity numbers — opt-in, off by default.
_REGIONAL_PATTERNS: dict[str, tuple[str, re.Pattern]] = {
    "us_ssn": ("ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    "uk_nino": ("nino", re.compile(r"\b[A-CEGHJ-PRSTW-Z]{2}\d{6}[A-D]\b", re.IGNORECASE)),
    "cn_id": ("cn_id", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
}


def _luhn_ok(value: str) -> bool:
    digits = [int(c) for c in value if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@dataclass
class PiiConfig:
    enabled_types: set[str] = field(
        default_factory=lambda: {"email", "api_key", "jwt", "phone", "credit_card"}
    )
    regional_types: set[str] = field(default_factory=set)  # keys of _REGIONAL_PATTERNS


@dataclass
class PiiMatch:
    type: str
    start: int
    end: int
    token: str

    def as_dict(self) -> dict:
        return {"type": self.type, "token": self.token}


@dataclass
class PiiResult:
    text: str                      # masked text (== original when nothing found)
    matches: list[PiiMatch] = field(default_factory=list)

    @property
    def types(self) -> list[str]:
        return sorted({m.type for m in self.matches})

    @property
    def found(self) -> bool:
        return bool(self.matches)

    def as_dict(self) -> dict:
        return {
            "found": self.found,
            "types": self.types,
            "count": len(self.matches),
            "tokens": [m.token for m in self.matches],
        }


def find_pii(text: str, config: PiiConfig | None = None) -> list[PiiMatch]:
    """Return raw matches (unmasked) — internal use only; never logged raw."""
    cfg = config or PiiConfig()
    candidates: list[tuple[str, int, int]] = []

    for type_name, pattern in _PATTERNS:
        if type_name not in cfg.enabled_types:
            continue
        for m in pattern.finditer(text):
            if type_name == "credit_card" and not _luhn_ok(m.group(0)):
                continue
            if type_name == "phone":
                digits = sum(c.isdigit() for c in m.group(0))
                if digits < 7:
                    continue
            candidates.append((type_name, m.start(), m.end()))

    for region in cfg.regional_types:
        if region in _REGIONAL_PATTERNS:
            type_name, pattern = _REGIONAL_PATTERNS[region]
            for m in pattern.finditer(text):
                candidates.append((type_name, m.start(), m.end()))

    # Resolve overlaps: keep earlier/longer spans.
    candidates.sort(key=lambda c: (c[1], -(c[2] - c[1])))
    accepted: list[tuple[str, int, int]] = []
    for type_name, start, end in candidates:
        if any(start < a_end and a_start < end for _, a_start, a_end in accepted):
            continue
        accepted.append((type_name, start, end))

    # Index per (type, value): the same identifier always maps to the same
    # token within one call, while distinct values get distinct tokens.
    counters: dict[str, int] = {}
    seen: dict[tuple[str, str], int] = {}
    matches: list[PiiMatch] = []
    for type_name, start, end in accepted:
        key = (type_name, text[start:end])
        if key not in seen:
            counters[type_name] = counters.get(type_name, 0) + 1
            seen[key] = counters[type_name]
        token = f"[{type_name.upper()}_{seen[key]}]"
        matches.append(PiiMatch(type=type_name, start=start, end=end, token=token))
    matches.sort(key=lambda m: m.start)
    return matches


def mask_pii(text: str, config: PiiConfig | None = None) -> PiiResult:
    """Detect and irreversibly mask PII in ``text`` (right-to-left splice)."""
    matches = find_pii(text, config)
    if not matches:
        return PiiResult(text=text, matches=[])
    masked = text
    for m in reversed(matches):
        masked = masked[: m.start] + m.token + masked[m.end:]
    return PiiResult(text=masked, matches=matches)
