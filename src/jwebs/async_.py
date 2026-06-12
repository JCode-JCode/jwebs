# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Any

from urllib3 import PoolManager, Timeout as Urllib3Timeout

from .core.datatypes import AsyncResponse


class AsyncClient:
    def __init__(self, max_connections: int = 100, timeout: float = 30.0,
                 connect_timeout: float = 10.0, default_headers: Optional[Dict] = None):
        import sys, os
        _default_max_connections = max_connections
        IS_ANDROID = hasattr(sys, 'getandroidapilevel') or 'ANDROID_STORAGE' in os.environ
        if IS_ANDROID:
            if max_connections == _default_max_connections:
                max_connections = min(max_connections, 20)
        else:
            if max_connections == _default_max_connections:
                max_connections = min(max_connections, 100)
        self.max_connections = max_connections
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.default_headers = default_headers or {
            'User-Agent': 'JWebs-Async/2.0',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate'
        }
        self._pool = PoolManager(
            num_pools=self.max_connections,
            maxsize=self.max_connections,
            headers=self.default_headers,
            timeout=Urllib3Timeout(connect=connect_timeout, read=timeout)
        )

    def GET(self, url: str, timeout: Optional[float] = None,
            connect_timeout: Optional[float] = None, **kwargs) -> AsyncResponse:
        start = time.time()
        try:
            headers = {**self.default_headers, **kwargs.pop('headers', {})}
            eff_connect = connect_timeout or self.connect_timeout
            eff_read = timeout or self.timeout
            resp = self._pool.request(
                'GET', url, headers=headers,
                timeout=Urllib3Timeout(connect=eff_connect, read=eff_read),
                **kwargs
            )
            elapsed = time.time() - start
            async_resp = AsyncResponse(
                status=resp.status, headers=dict(resp.headers),
                body=resp.data, url=url, elapsed=elapsed,
                content_type=resp.headers.get('Content-Type', '')
            )
            resp.release_conn()
            return async_resp
        except Exception as e:
            return AsyncResponse(
                status=0, headers={}, body=str(e).encode(),
                url=url, elapsed=time.time() - start, content_type='text/plain'
            )

    def POST(self, url: str, json: Optional[Dict] = None,
             data: Optional[Any] = None, timeout: Optional[float] = None,
             **kwargs) -> AsyncResponse:
        start = time.time()
        try:
            headers = {**self.default_headers, **kwargs.pop('headers', {})}
            if json:
                body = json.dumps(json).encode('utf-8')
                headers['Content-Type'] = 'application/json'
                resp = self._pool.request('POST', url, headers=headers, body=body,
                                        timeout=Urllib3Timeout(connect=self.connect_timeout,
                                                               read=timeout or self.timeout))
            else:
                resp = self._pool.request('POST', url, headers=headers, body=data,
                                        timeout=Urllib3Timeout(connect=self.connect_timeout,
                                                               read=timeout or self.timeout))
            elapsed = time.time() - start
            async_resp = AsyncResponse(
                status=resp.status, headers=dict(resp.headers),
                body=resp.data, url=url, elapsed=elapsed,
                content_type=resp.headers.get('Content-Type', '')
            )
            resp.release_conn()
            return async_resp
        except Exception as e:
            return AsyncResponse(
                status=0, headers={}, body=str(e).encode(),
                url=url, elapsed=time.time() - start, content_type='text/plain'
            )

    def BATCH_GET(self, urls: List[str], **kwargs) -> Dict[str, AsyncResponse]:
        results = {}
        def fetch(url):
            return url, self.GET(url, **kwargs)
        with ThreadPoolExecutor(max_workers=self.max_connections) as executor:
            futures = [executor.submit(fetch, url) for url in urls]
            for future in as_completed(futures):
                url, result = future.result()
                results[url] = result
        return results

    def CLOSE(self):
        self._pool.clear()