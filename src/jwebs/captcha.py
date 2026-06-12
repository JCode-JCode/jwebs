# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import os
import json
import time
import threading
from typing import Optional, List

from urllib3 import PoolManager, Timeout as Urllib3Timeout, Retry

from .core.datatypes import CAPTCHAResult
from .core.logging import logger

class CaptchaSolver:
    def __init__(self, api_key: Optional[str] = None, service: str = '2captcha',
                 connect_timeout: float = 10.0, read_timeout: float = 30.0,
                 solve_timeout: float = 180.0):
        self.api_key = api_key or os.environ.get('CAPTCHA_API_KEY', '')
        self.service = service
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.solve_timeout = solve_timeout
        self.solve_history: List[CAPTCHAResult] = []
        self._lock = threading.Lock()

        self._pool = PoolManager(
            num_pools=2, maxsize=5,
            timeout=Urllib3Timeout(connect=connect_timeout, read=read_timeout),
            retries=Retry(total=3, backoff_factor=1.0),
            cert_reqs='CERT_REQUIRED'
        )

    def set_timeouts(self, connect: Optional[float] = None, read: Optional[float] = None,
                     solve: Optional[float] = None):
        if connect is not None:
            self.connect_timeout = connect
        if read is not None:
            self.read_timeout = read
        if solve is not None:
            self.solve_timeout = solve
        self._pool = PoolManager(
            num_pools=2, maxsize=5,
            timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout),
            retries=Retry(total=3, backoff_factor=1.0),
            cert_reqs='CERT_REQUIRED'
        )

    def DETECT(self, html: str) -> Optional[str]:
        html_lower = html.lower()
        if 'g-recaptcha' in html_lower or 'recaptcha' in html_lower:
            return 'recaptcha_v2'
        if 'h-captcha' in html_lower or 'hcaptcha' in html_lower:
            return 'hcaptcha'
        if 'captcha' in html_lower:
            return 'image_captcha'
        return None

    def SOLVE(self, site_key: str, page_url: str) -> CAPTCHAResult:
        start_time = time.time()
        if not self.api_key:
            return CAPTCHAResult(solved=False, provider='none', time_taken=time.time() - start_time)
        try:
            payload = {
                'key': self.api_key, 'method': 'userrecaptcha',
                'googlekey': site_key, 'pageurl': page_url, 'json': 1
            }
            resp = self._pool.request(
                'POST', 'https://2captcha.com/in.php', fields=payload,
                timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout)
            )
            result_data = json.loads(resp.data.decode('utf-8'))
            resp.release_conn()
            if result_data.get('status') != 1:
                return CAPTCHAResult(solved=False, provider=self.service, time_taken=time.time() - start_time)

            captcha_id = result_data['request']
            deadline = time.time() + self.solve_timeout

            for attempt in range(60):
                if time.time() > deadline:
                    return CAPTCHAResult(solved=False, provider=self.service,
                                        time_taken=time.time() - start_time, attempts=attempt)
                time.sleep(5)
                resp = self._pool.request(
                    'GET', 'https://2captcha.com/res.php',
                    fields={'key': self.api_key, 'action': 'get', 'id': captcha_id, 'json': 1},
                    timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout)
                )
                result_data = json.loads(resp.data.decode('utf-8'))
                resp.release_conn()
                if result_data.get('status') == 1:
                    return CAPTCHAResult(
                        solved=True, solution=result_data['request'],
                        provider=self.service, time_taken=time.time() - start_time,
                        attempts=attempt + 1
                    )
        except Exception as e:
            logger.error('CaptchaSolver', f"Error: {e}", exc_info=True)
        return CAPTCHAResult(solved=False, provider=self.service, time_taken=time.time() - start_time)