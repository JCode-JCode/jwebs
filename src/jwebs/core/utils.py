# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import re
from collections import Counter
from typing import Optional
from bs4 import BeautifulSoup

from .constants import RE_WORD

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def cosine_similarity(text1: str, text2: str) -> float:
    tokens1 = RE_WORD.findall(str(text1).lower())
    tokens2 = RE_WORD.findall(str(text2).lower())
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    freq1 = Counter(tokens1)
    freq2 = Counter(tokens2)
    all_words = set(freq1.keys()) | set(freq2.keys())
    vec1 = [freq1.get(word, 0) for word in all_words]
    vec2 = [freq2.get(word, 0) for word in all_words]
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sum(a * a for a in vec1) ** 0.5
    magnitude2 = sum(b * b for b in vec2) ** 0.5
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)

def _safe_parse_html(html: str, features: str = 'lxml') -> BeautifulSoup:
    try:
        return BeautifulSoup(html, features)
    except Exception:
        return BeautifulSoup(html, 'html.parser')