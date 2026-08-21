from __future__ import annotations

from jamo import h2j, j2hcj


def decompose(word: str) -> str:
    """Decompose Hangul to a jamo string; non-Hangul characters pass through."""
    parts: list[str] = []
    for ch in word:
        if "가" <= ch <= "힣":
            parts.append(j2hcj(h2j(ch)))
        else:
            parts.append(ch)
    return "".join(parts)


def jamo_distance(a: str, b: str) -> int:
    ja, jb = decompose(a), decompose(b)
    m, n = len(ja), len(jb)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        curr = [i] + [0] * n
        for j in range(1, n + 1):
            if ja[i - 1] == jb[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr
    return prev[n]


def similarity_threshold(word: str) -> int:
    """Max allowed jamo edit distance: 1 for ≤3 syllables, 2 for ≥4."""
    syllables = sum(1 for ch in word if "가" <= ch <= "힣")
    return 1 if syllables <= 3 else 2
