# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import re
import base64
import hashlib
from collections import Counter
from typing import Optional, Dict, Union, Tuple
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

def encode_auth(user: str, password: str, encoding: str = "base64") -> str:
    credentials = f"{user}:{password}".encode('utf-8')
    if encoding == "base64":
        return base64.b64encode(credentials).decode('utf-8')
    elif encoding == "base85":
        return base64.b85encode(credentials).decode('utf-8')
    elif encoding.startswith("hash-"):
        algo_name = encoding.split("-", 1)[1]
        try:
            hash_func = getattr(hashlib, algo_name)
        except AttributeError:
            raise ValueError(f"Unsupported hash algorithm: {algo_name}. Use sha256, sha512, md5, sha1, etc.")
        hashed = hash_func(credentials).digest()
        return base64.b64encode(hashed).decode('utf-8')
    else:
        raise ValueError(
            f"Unsupported encoding: {encoding}. Use 'base64', 'base85', or 'hash-*' (e.g., hash-sha256)."
        )

def parse_auth(auth: Optional[Union[Tuple[str, str], Dict, bool]]) -> Optional[Dict]:
    if auth is None or auth is False:
        return None
    if isinstance(auth, tuple) and len(auth) == 2:
        user, password = auth
        encoding = "base64"
    elif isinstance(auth, dict):
        user = auth.get("user")
        password = auth.get("password")
        encoding = auth.get("encoding", "base64")
        if not user or not password:
            raise ValueError("auth dict must contain 'user' and 'password' keys")
    else:
        raise TypeError(
            "auth must be None, False, a tuple (user, password), or a dict with 'user', 'password', 'encoding'"
        )
    encode_auth(user, password, encoding)
    return {"user": user, "password": password, "encoding": encoding}
