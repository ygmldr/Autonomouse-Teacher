"""Conservative deterministic solution leakage checks, not a semantic proof."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LeakageResult:
    status: str  # CLEAR / LEAK / NEEDS_REVIEW
    reason: str


def check_solution_leakage(text: str) -> LeakageResult:
    code_blocks = re.findall(r"```[^\n]*\n(.*?)```", text, flags=re.S)
    suspicious = code_blocks or [text]
    for block in suspicious:
        # Representative complete Python/C++/Java programs and function solutions.
        function = re.search(r"\bdef\s+\w+\s*\(|\b(?:int|void|long)\s+(?:main|solve)\s*\(|\bclass\s+Solution\b", block)
        output = re.search(r"\breturn\b|\bprint\s*\(|\bcout\s*<<|\bSystem\.out", block)
        flow = re.search(r"\bfor\b|\bwhile\b|\bif\b|\breturn\b", block)
        if function and output and flow:
            return LeakageResult("LEAK", "complete function/program pattern")
        if re.search(r"\binput\s*\(", block) and output and flow:
            return LeakageResult("LEAK", "executable input/output algorithm pattern")
    if re.search(r"(?:complete (?:solution|answer)|full (?:solution|code))\s*:", text, re.I):
        return LeakageResult("LEAK", "explicit full-answer marker")
    if code_blocks or "```" in text or re.search(r"\b(?:def\s+\w+|while\s*\(|for\s*\()|(?:^|\n)\s*return\s+\w+", text):
        return LeakageResult("NEEDS_REVIEW", "partial code or ambiguous pseudocode")
    return LeakageResult("CLEAR", "no representative leakage pattern; not a semantic guarantee")
