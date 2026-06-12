# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import hashlib
import time
import threading
from typing import Dict

from .core.utils import cosine_similarity

class ContentDiffer:
    def __init__(self):
        self.snapshots: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def TAKE_SNAPSHOT(self, name: str, content: str) -> str:
        snapshot_id = hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()
        with self._lock:
            self.snapshots[snapshot_id] = {
                'name': name,
                'content': content,
                'timestamp': time.time(),
                'hash': hashlib.md5(content.encode()).hexdigest(),
                'word_count': len(content.split()),
            }
        return snapshot_id

    def COMPARE(self, id1: str, id2: str) -> Dict:
        with self._lock:
            if id1 not in self.snapshots or id2 not in self.snapshots:
                return {}
            snap1, snap2 = self.snapshots[id1], self.snapshots[id2]
        words1 = set(snap1['content'].split())
        words2 = set(snap2['content'].split())
        return {
            'snapshot1': snap1['name'],
            'snapshot2': snap2['name'],
            'hash_changed': snap1['hash'] != snap2['hash'],
            'word_count_diff': snap2['word_count'] - snap1['word_count'],
            'words_added': list(words2 - words1)[:50],
            'words_removed': list(words1 - words2)[:50],
            'similarity_ratio': len(words1 & words2) / max(1, len(words1 | words2)),
            'time_diff': snap2['timestamp'] - snap1['timestamp']
        }

    def SIMILARITY(self, text1: str, text2: str) -> float:
        return cosine_similarity(text1, text2)

    def CLEAR(self):
        with self._lock:
            self.snapshots.clear()