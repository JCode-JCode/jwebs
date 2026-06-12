# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import json
import sqlite3
import threading
import time
from typing import Optional, Any, Dict

from .datatypes import CacheEntry
from .constants import DEFAULT_CACHE_TTL, MAX_MEMORY_ENTRIES, DEFAULT_MEMORY_TTL
from .exceptions import CacheError
from .logging import logger

class CacheManager:
    def __init__(self, db_path: str = 'jwebs_cache.db', memory_ttl: float = DEFAULT_MEMORY_TTL,
                 max_memory_entries: int = MAX_MEMORY_ENTRIES,
                 max_item_size: Optional[int] = 5 * 1024 * 1024):
        self.db_path = db_path
        self.memory_ttl = memory_ttl
        self.max_memory_entries = max_memory_entries
        self.max_item_size = max_item_size
        self.memory_cache: Dict[str, CacheEntry] = {}
        self.lock = threading.RLock()
        self._db_available = False
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute('''CREATE TABLE IF NOT EXISTS cache (
                    url TEXT PRIMARY KEY, data_json TEXT, timestamp REAL,
                    ttl REAL, etag TEXT, last_modified TEXT
                )''')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON cache(timestamp)')
                conn.commit()
            self._db_available = True
        except sqlite3.Error as e:
            logger.error('CacheManager', f"Database init failed: {e}", exc_info=True)

    def get(self, url: str) -> Optional[Any]:
        with self.lock:
            if url in self.memory_cache:
                entry = self.memory_cache[url]
                if entry.ttl is None:
                    return entry.data
                if time.time() - entry.timestamp < entry.ttl:
                    return entry.data
                del self.memory_cache[url]
        if not self._db_available:
            return None
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    'SELECT data_json, timestamp, ttl FROM cache WHERE url = ?', (url,)
                )
                row = cursor.fetchone()
                if row:
                    ttl = row[2]
                    if ttl is None:
                        try:
                            data = json.loads(row[0])
                        except (json.JSONDecodeError, TypeError):
                            data = row[0]
                        with self.lock:
                            self.memory_cache[url] = CacheEntry(data=data, timestamp=row[1], ttl=ttl)
                        return data
                    elif time.time() - row[1] < ttl:
                        try:
                            data = json.loads(row[0])
                        except (json.JSONDecodeError, TypeError):
                            data = row[0]
                        with self.lock:
                            self.memory_cache[url] = CacheEntry(data=data, timestamp=row[1], ttl=ttl)
                        return data
                    else:
                        conn.execute('DELETE FROM cache WHERE url = ?', (url,))
                        conn.commit()
        except sqlite3.Error as e:
            logger.error('CacheManager', f"DB read failed: {e}", exc_info=True)
        return None

    def set(self, url: str, data: Any, ttl: float = DEFAULT_CACHE_TTL,
            etag: Optional[str] = None, last_modified: Optional[str] = None):
        # Check item size if limit is set
        if self.max_item_size is not None:
            try:
                if isinstance(data, bytes):
                    size = len(data)
                elif isinstance(data, str):
                    size = len(data.encode('utf-8'))
                else:
                    size = len(json.dumps(data, ensure_ascii=False).encode('utf-8'))
                if size > self.max_item_size:
                    logger.debug('CacheManager', f"Item too large ({size} bytes), not caching {url}")
                    return
            except Exception:
                pass

        entry = CacheEntry(data=data, timestamp=time.time(), ttl=ttl,
                           etag=etag, last_modified=last_modified)
        with self.lock:
            self.memory_cache[url] = entry
            if len(self.memory_cache) > self.max_memory_entries:
                self._cleanup_memory()
        if not self._db_available:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                try:
                    data_json = json.dumps(data, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    data_json = json.dumps(str(data), ensure_ascii=False)
                conn.execute(
                    'INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?, ?)',
                    (url, data_json, entry.timestamp, ttl, etag, last_modified)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error('CacheManager', f"DB write failed: {e}", exc_info=True)

    def _cleanup_memory(self):
        now = time.time()
        expired = [k for k, v in self.memory_cache.items() if v.ttl is not None and now - v.timestamp > v.ttl]
        for k in expired:
            del self.memory_cache[k]
        if len(self.memory_cache) > self.max_memory_entries:
            sorted_entries = sorted(self.memory_cache.items(), key=lambda x: x[1].timestamp)
            excess = len(self.memory_cache) - self.max_memory_entries
            for k, _ in sorted_entries[:excess]:
                del self.memory_cache[k]

    def _cleanup_db(self):
        if not self._db_available:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM cache WHERE ttl IS NOT NULL AND timestamp + ttl < ?', (time.time(),))
                conn.commit()
        except sqlite3.Error as e:
            logger.error('CacheManager', f"DB cleanup failed: {e}", exc_info=True)

    def clear(self):
        with self.lock:
            self.memory_cache.clear()
        if not self._db_available:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM cache')
                conn.commit()
        except sqlite3.Error as e:
            logger.error('CacheManager', f"Cache clear failed: {e}", exc_info=True)

    def get_stats(self) -> Dict:
        with self.lock:
            memory_count = len(self.memory_cache)
        db_count = 0
        if self._db_available:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute('SELECT COUNT(*) FROM cache')
                    db_count = cursor.fetchone()[0]
            except sqlite3.Error:
                pass
        return {
            'memory_entries': memory_count,
            'db_entries': db_count,
            'max_memory_entries': self.max_memory_entries,
            'max_item_size': self.max_item_size,
        }