# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import time
import threading
import hashlib
from collections import defaultdict
from typing import Dict, List, Optional

from .core.http import FastHTTP
from .core.logging import logger
from .core.constants import MONITOR_DEFAULT_INTERVAL

class Monitor:
    def __init__(self, check_interval: int = MONITOR_DEFAULT_INTERVAL, check_timeout: float = 10.0):
        self.check_interval = check_interval
        self.check_timeout = check_timeout
        self._monitored_urls: Dict[str, Dict] = {}
        self._check_history: Dict[str, List[Dict]] = defaultdict(list)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.http = FastHTTP()

    def ADD_URL(self, url: str, expected_status: int = 200) -> str:
        url_id = hashlib.md5(url.encode()).hexdigest()[:12]
        with self._lock:
            self._monitored_urls[url_id] = {
                'url': url, 'expected_status': expected_status,
                'added_at': time.time(), 'last_check': None,
                'last_status': None, 'is_up': None,
                'total_checks': 0, 'failures': 0
            }
        return url_id

    def REMOVE_URL(self, url_id: str):
        with self._lock:
            self._monitored_urls.pop(url_id, None)
            self._check_history.pop(url_id, None)

    def CHECK_URL(self, url_id: str) -> Dict:
        with self._lock:
            if url_id not in self._monitored_urls:
                return {'error': 'URL not found'}
            info = self._monitored_urls[url_id]
            url = info['url']

        start_time = time.time()
        result = {'url': url, 'timestamp': time.time(), 'status_code': None,
                  'response_time': 0, 'is_up': False, 'error': None}

        try:
            resp = self.http.GET(url, timeout=self.check_timeout)
            elapsed = time.time() - start_time
            result['response_time'] = elapsed
            result['status_code'] = resp.status if resp else None
            result['is_up'] = resp is not None and resp.status == info['expected_status']
        except Exception as e:
            result['error'] = str(e)
            result['response_time'] = time.time() - start_time

        with self._lock:
            info.update(
                last_check=result['timestamp'],
                last_status=result['status_code'],
                is_up=result['is_up']
            )
            info['total_checks'] += 1
            if not result['is_up']:
                info['failures'] += 1
            self._check_history[url_id].append(result)

        return result

    def START(self):
        if self._running:
            return
        self._running = True
        def loop():
            while self._running:
                try:
                    with self._lock:
                        url_ids = list(self._monitored_urls.keys())
                    for url_id in url_ids:
                        self.CHECK_URL(url_id)
                except Exception as e:
                    logger.error('Monitor', f"Loop error: {e}", exc_info=True)
                time.sleep(self.check_interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def STOP(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)