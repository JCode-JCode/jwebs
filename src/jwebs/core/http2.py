# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import time
import json
import threading
import logging
from collections import deque
from typing import Optional, Dict, Any, List, Tuple, Union, Callable
from urllib.parse import urlparse, urljoin

import httpx
from httpx import Limits, Timeout as HttpxTimeout

from .http import HTTPResponse
from .cache import CacheManager
from .ratelimit import RateLimiter
from .robots import RobotsParser
from .session import SessionManager
from .logging import logger
from .constants import (
    DEFAULT_CACHE_TTL, DEFAULT_RATE_LIMIT, DEFAULT_RATE_LIMIT_TIMEOUT,
    DEFAULT_SESSION_IDLE_TIMEOUT, DEFAULT_NUM_POOLS, DEFAULT_POOL_MAXSIZE,
    DEFAULT_MAX_WORKERS, DEFAULT_HTTP_TIMEOUT, DEFAULT_CONNECT_TIMEOUT
)
from .exceptions import JWebsError, JWebsTimeoutError, RobotsBlockedError

class HTTPXClient:
    _DEFAULT_UA_LIST = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Android 14; Mobile; rv:125.0) Gecko/125.0 Firefox/125.0',
    ]

    def __init__(self,
                 http_version: str = 'auto',
                 timeout: float = DEFAULT_HTTP_TIMEOUT,
                 connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
                 verify_ssl: bool = True,
                 default_headers: Optional[Dict] = None,
                 use_cache: bool = False,
                 cache_ttl: float = DEFAULT_CACHE_TTL,
                 cache_max_item_size: Optional[int] = 5 * 1024 * 1024,
                 rate_limit: float = DEFAULT_RATE_LIMIT,
                 rate_limit_timeout: float = DEFAULT_RATE_LIMIT_TIMEOUT,
                 respect_robots_txt: bool = False,
                 robots_user_agent: str = 'JWebs/2.0',
                 robots_timeout: float = 5.0,
                 use_proxy: bool = False,
                 proxy_rotator: Optional[Any] = None,
                 session_idle_timeout: float = DEFAULT_SESSION_IDLE_TIMEOUT,
                 allow_expired_sessions: bool = False,
                 max_connections: int = DEFAULT_MAX_WORKERS * 2,
                 max_redirects: int = 30,
                 retry_total: int = 0,
                 retry_backoff: float = 0.1,
                 retry_status_forcelist: Optional[List[int]] = None,
                 use_random_ua: bool = False,
                 ua_list: Optional[List[str]] = None,
                 referrer: Optional[str] = None,
                 enable_logging: bool = False,
                 log_dir: str = 'logs',
                 log_level: int = logging.INFO,
                 log_console: bool = True,
                 suppress_ssl_warnings: bool = True):

        self.http_version = http_version
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.verify_ssl = verify_ssl
        self.default_headers = default_headers or {}
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self.cache_max_item_size = cache_max_item_size
        self.rate_limiter = RateLimiter(rate_limit, rate_limit_timeout)
        self.respect_robots = respect_robots_txt
        self.robots_parser = RobotsParser(user_agent=robots_user_agent, timeout=robots_timeout) if respect_robots_txt else None
        self.use_proxy = use_proxy
        self.proxy_rotator = proxy_rotator
        self.session_manager = SessionManager(session_idle_timeout)
        self.allow_expired_sessions = allow_expired_sessions
        self.max_connections = max_connections
        self.max_redirects = max_redirects
        self.retry_total = retry_total
        self.retry_backoff = retry_backoff
        if retry_status_forcelist is None:
            self.retry_status_forcelist = [429, 500, 502, 503, 504]
        else:
            self.retry_status_forcelist = retry_status_forcelist
        self.use_random_ua = use_random_ua
        if ua_list:
            self._ua_list = ua_list.copy()
        else:
            self._ua_list = self._DEFAULT_UA_LIST.copy()
        if not self._ua_list:
            self._ua_list = [self._DEFAULT_UA_LIST[0]]
        self._ua_index = 0
        self._ua_lock = threading.Lock()
        self.referrer = referrer
        self.cache = CacheManager(max_item_size=cache_max_item_size) if use_cache else None
        self._client = None
        self._lock = threading.Lock()
        self._current_proxy = None
        self._last_response: Optional[HTTPResponse] = None
        self._last_response_lock = threading.Lock()
        self._history: deque = deque(maxlen=1000)
        self._history_lock = threading.Lock()
        self._hooks: Dict[str, List[Callable]] = {
            'before_request': [],
            'after_request': [],
            'on_error': [],
            'on_retry': [],
            'on_blocked': []
        }
        self._features = {
            'history': True,
            'hooks': True,
            'robots': respect_robots_txt,
            'rate_limit': rate_limit > 0,
            'cache': use_cache,
            'session': True,
            'ua_rotation': use_random_ua,
        }
        self._features_lock = threading.Lock()
        self.quick_mode = False
        self._quick_mode_lock = threading.Lock()

        if suppress_ssl_warnings:
            try:
                import urllib3
                from urllib3.exceptions import InsecureRequestWarning
                urllib3.disable_warnings(InsecureRequestWarning)
            except ImportError:
                pass

        logger.configure(enabled=enable_logging, log_dir=log_dir,
                         level=log_level, console=log_console)

    def _get_feature(self, name: str) -> bool:
        with self._features_lock:
            return self._features.get(name, False)

    def _get_next_ua(self) -> str:
        if not self._ua_list:
            return self.default_headers.get('User-Agent', 'JWebs/2.0')
        if not self._get_feature('ua_rotation'):
            return self.default_headers.get('User-Agent', self._ua_list[0])
        with self._ua_lock:
            ua = self._ua_list[self._ua_index]
            self._ua_index = (self._ua_index + 1) % len(self._ua_list)
            return ua

    def _build_headers(self, headers: Optional[Dict] = None,
                       session_id: Optional[str] = None) -> Dict:
        final_headers = self.default_headers.copy()
        final_headers['User-Agent'] = self._get_next_ua()
        if self.referrer:
            final_headers['Referer'] = self.referrer
        if headers:
            final_headers.update(headers)
        if session_id and self._get_feature('session'):
            if self.allow_expired_sessions:
                if session_id in self.session_manager.sessions:
                    session_data = self.session_manager.sessions[session_id]
                    final_headers.update(session_data.get('headers', {}))
                    cookies = session_data.get('cookies', {})
                    if cookies:
                        final_headers['Cookie'] = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            else:
                session_data = self.session_manager.get_session(session_id)
                if session_data:
                    final_headers.update(session_data.get('headers', {}))
                    cookies = session_data.get('cookies', {})
                    if cookies:
                        final_headers['Cookie'] = '; '.join([f"{k}={v}" for k, v in cookies.items()])
        return final_headers

    def _execute_hooks(self, hook_type: str, **kwargs):
        if not self._get_feature('hooks'):
            return
        for hook in self._hooks.get(hook_type, []):
            try:
                hook(**kwargs)
            except Exception as e:
                logger.error('HTTPXClient', f"Hook '{hook_type}' failed: {e}", exc_info=True)

    def _record_request(self, method: str, url: str, status: Optional[int],
                        duration: float, error: Optional[str] = None,
                        headers_received: Optional[Dict] = None):
        if not self._get_feature('history'):
            return
        from .datatypes import RequestRecord
        record = RequestRecord(method=method, url=url, status=status,
                               duration=duration, error=error,
                               headers_received=headers_received or {})
        with self._history_lock:
            self._history.append(record)

    def _get_client(self) -> httpx.Client:
        with self._lock:
            proxy_url = None
            if self.use_proxy and self.proxy_rotator:
                proxy_dict = self.proxy_rotator.GET_PROXY()
                if proxy_dict and 'http' in proxy_dict:
                    proxy_url = proxy_dict.get('http')
            if self._client is None or self._current_proxy != proxy_url:
                if self._client is not None:
                    self._client.close()
                limits = Limits(max_connections=self.max_connections,
                                max_keepalive_connections=self.max_connections)
                timeout_config = HttpxTimeout(self.timeout, connect=self.connect_timeout)
                self._client = httpx.Client(
                    http2=(self.http_version == '2'),
                    timeout=timeout_config,
                    verify=self.verify_ssl,
                    headers=self.default_headers,
                    limits=limits,
                    proxy=proxy_url,
                    max_redirects=0
                )
                self._current_proxy = proxy_url
            return self._client

    def _check_robots(self, url: str) -> bool:
        if self.respect_robots and self.robots_parser:
            return self.robots_parser.is_allowed(url)
        return True

    def _get_cache_ttl(self, headers: Dict) -> float:
        cache_control = headers.get('Cache-Control', '') or headers.get('cache-control', '')
        if 'max-age=' in cache_control:
            try:
                return float(cache_control.split('max-age=')[1].split(',')[0])
            except (ValueError, IndexError):
                pass
        return self.cache_ttl

    def _do_request(self, method: str, url: str,
                    headers: Optional[Dict] = None,
                    json: Any = None,
                    data: Any = None,
                    params: Optional[Dict] = None,
                    session_id: Optional[str] = None,
                    respect_robots: Optional[bool] = None,
                    timeout: Optional[float] = None,
                    redirects: Optional[Union[bool, int]] = None,
                    stream: bool = False,
                    raise_on_error: bool = False,
                    auto_decompress: bool = True,
                    **kwargs) -> HTTPResponse:
        start_time = time.monotonic()
        with self._quick_mode_lock:
            if self.quick_mode:
                return self._quick_request(method, url, headers, json, data, params,
                                           timeout, redirects, raise_on_error, **kwargs)

        check_robots = respect_robots if respect_robots is not None else self._get_feature('robots')
        if check_robots and not self._check_robots(url):
            if self._get_feature('hooks'):
                self._execute_hooks('on_blocked', method=method, url=url, reason='robots.txt')
            err_msg = f"Blocked by robots.txt: {url}"
            logger.warning('HTTPXClient', err_msg)
            if raise_on_error:
                raise RobotsBlockedError(url)
            return HTTPResponse(status=403, url=url, error=err_msg, elapsed=0)

        if self._get_feature('rate_limit') and not self.rate_limiter.wait_and_acquire():
            err_msg = f"Rate limit timeout for URL: {url}"
            logger.error('HTTPXClient', err_msg)
            if raise_on_error:
                raise JWebsTimeoutError(err_msg)
            return HTTPResponse(status=429, url=url, error=err_msg, elapsed=0)

        if self._get_feature('hooks'):
            self._execute_hooks('before_request', method=method, url=url)

        if method.upper() == 'GET' and self._get_feature('cache') and self.cache:
            cached = self.cache.get(url)
            if cached is not None:
                data_bytes = cached if isinstance(cached, bytes) else str(cached).encode()
                resp = HTTPResponse(status=200, data=data_bytes, url=url, elapsed=0)
                with self._last_response_lock:
                    self._last_response = resp
                return resp

        client = self._get_client()
        final_headers = self._build_headers(headers, session_id)
        use_redirects = self.max_redirects if redirects is None else (redirects if isinstance(redirects, int) else (30 if redirects else 0))
        current_url = url
        current_method = method.upper()
        current_headers = final_headers
        current_json = json
        current_data = data
        current_params = params
        last_response = None
        hop = 0

        while hop <= use_redirects:
            try:
                resp = client.request(
                    method=current_method,
                    url=current_url,
                    headers=current_headers,
                    json=current_json,
                    data=current_data,
                    params=current_params,
                    timeout=timeout or self.timeout,
                    follow_redirects=False,
                    **kwargs
                )
                if resp.status_code in (301, 302, 303, 307, 308) and hop < use_redirects:
                    location = resp.headers.get('Location')
                    if not location:
                        last_response = resp
                        break
                    current_url = urljoin(current_url, location)
                    if resp.status_code in (301, 302, 303):
                        current_method = 'GET'
                        current_json = None
                        current_data = None
                        current_params = None
                        current_headers.pop('Content-Type', None)
                        current_headers.pop('Content-Length', None)
                    hop += 1
                    continue
                else:
                    last_response = resp
                    break
            except Exception as e:
                last_response = None
                break

        elapsed = time.monotonic() - start_time
        if last_response is None:
            error_msg = "No response or request failed"
            self._record_request(method, url, 0, elapsed, error=error_msg)
            if raise_on_error:
                raise JWebsError(error_msg)
            return HTTPResponse(status=0, url=url, error=error_msg, elapsed=elapsed)

        content = last_response.content
        status = last_response.status_code
        headers_dict = dict(last_response.headers)

        if self.retry_total > 0 and status in self.retry_status_forcelist:
            for attempt in range(self.retry_total):
                if self._get_feature('hooks'):
                    self._execute_hooks('on_retry', attempt=attempt+1, url=url, status=status)
                time.sleep(self.retry_backoff * (2 ** attempt))
                try:
                    new_resp = client.request(
                        method=current_method,
                        url=current_url,
                        headers=current_headers,
                        json=current_json,
                        data=current_data,
                        params=current_params,
                        timeout=timeout or self.timeout,
                        follow_redirects=False
                    )
                    if new_resp.status_code not in self.retry_status_forcelist:
                        content = new_resp.content
                        status = new_resp.status_code
                        headers_dict = dict(new_resp.headers)
                        break
                except Exception:
                    continue

        if method.upper() == 'GET' and self._get_feature('cache') and self.cache and status == 200:
            ttl = self._get_cache_ttl(headers_dict)
            self.cache.set(url, content, ttl=ttl,
                           etag=headers_dict.get('ETag'),
                           last_modified=headers_dict.get('Last-Modified'))

        if session_id and self._get_feature('session'):
            self.session_manager.update_from_response(session_id, headers_dict)

        response = HTTPResponse(status=status, data=content, headers=headers_dict,
                                url=current_url, elapsed=elapsed, auto_decompress=auto_decompress)
        with self._last_response_lock:
            self._last_response = response
        self._record_request(method, url, status, elapsed, headers_received=headers_dict)

        if self._get_feature('hooks'):
            self._execute_hooks('after_request', method=method, url=url,
                                response=response, duration=elapsed)

        if raise_on_error and (response.is_client_error or response.is_server_error):
            response.raise_for_status()

        return response

    def _quick_request(self, method: str, url: str,
                       headers: Optional[Dict] = None,
                       json: Any = None,
                       data: Any = None,
                       params: Optional[Dict] = None,
                       timeout: Optional[float] = None,
                       redirects: Optional[Union[bool, int]] = None,
                       raise_on_error: bool = False,
                       **kwargs) -> HTTPResponse:
        start = time.monotonic()
        client = self._get_client()
        max_redirs = self.max_redirects if redirects is None else (redirects if isinstance(redirects, int) else (30 if redirects else 0))
        try:
            current_method = method.upper()
            current_url = url
            current_headers = headers or {}
            current_json = json
            current_data = data
            current_params = params

            for _ in range(max_redirs + 1):
                resp = client.request(method=current_method, url=current_url,
                                      headers=current_headers, json=current_json,
                                      data=current_data, params=current_params,
                                      timeout=timeout or self.timeout, follow_redirects=False)
                if resp.status_code in (301, 302, 303, 307, 308) and _ < max_redirs:
                    location = resp.headers.get('Location')
                    if not location:
                        break
                    current_url = urljoin(current_url, location)
                    if resp.status_code in (301, 302, 303):
                        current_method = 'GET'
                        current_json = None
                        current_data = None
                        current_params = None
                else:
                    elapsed = time.monotonic() - start
                    content = resp.content
                    response = HTTPResponse(status=resp.status_code, data=content,
                                            headers=dict(resp.headers), url=str(resp.url),
                                            elapsed=elapsed, auto_decompress=True)
                    if raise_on_error and (response.is_client_error or response.is_server_error):
                        response.raise_for_status()
                    return response
            elapsed = time.monotonic() - start
            return HTTPResponse(status=0, url=url, error="Too many redirects", elapsed=elapsed)
        except Exception as e:
            elapsed = time.monotonic() - start
            err_msg = str(e)
            if raise_on_error:
                raise JWebsError(err_msg)
            return HTTPResponse(status=0, url=url, error=err_msg, elapsed=elapsed)

    def GET(self, url: str, **kwargs) -> HTTPResponse:
        return self._do_request('GET', url, **kwargs)

    def POST(self, url: str, **kwargs) -> HTTPResponse:
        return self._do_request('POST', url, **kwargs)

    def PUT(self, url: str, **kwargs) -> HTTPResponse:
        return self._do_request('PUT', url, **kwargs)

    def PATCH(self, url: str, **kwargs) -> HTTPResponse:
        return self._do_request('PATCH', url, **kwargs)

    def DELETE(self, url: str, **kwargs) -> HTTPResponse:
        return self._do_request('DELETE', url, **kwargs)

    def HEAD(self, url: str, **kwargs) -> HTTPResponse:
        return self._do_request('HEAD', url, **kwargs)

    def OPTIONS(self, url: str, **kwargs) -> HTTPResponse:
        return self._do_request('OPTIONS', url, **kwargs)

    def TEXT(self, url: str, raise_on_error: bool = True, **kwargs) -> Optional[str]:
        resp = self.GET(url, raise_on_error=raise_on_error, **kwargs)
        if resp and resp.status > 0:
            return resp.text
        if raise_on_error:
            raise JWebsError(f"Failed to get text from {url}: {resp.error if resp else 'No response'}")
        return None

    def JSON(self, url: str, raise_on_error: bool = True, **kwargs) -> Optional[Any]:
        resp = self.GET(url, raise_on_error=raise_on_error, **kwargs)
        if resp and resp.status > 0:
            return resp.JSON()
        if raise_on_error:
            raise JWebsError(f"Failed to get JSON from {url}: {resp.error if resp else 'No response'}")
        return None

    def BATCH(self, urls: List[str], method: str = 'GET', max_workers: Optional[int] = None,
              raise_on_error: bool = False, **kwargs) -> Dict[str, Any]:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        max_workers = max_workers or (self.max_connections // 2)
        results = {}
        method_func = getattr(self, method.upper(), self.GET)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(method_func, url, raise_on_error=False, **kwargs): url for url in urls}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    logger.error('HTTPXClient', f"Batch error for {url}: {e}", exc_info=True)
                    if raise_on_error:
                        raise
                    results[url] = HTTPResponse(status=0, url=url, error=str(e))
        return results

    def set_timeout(self, timeout: float, connect_timeout: Optional[float] = None):
        self.timeout = timeout
        if connect_timeout is not None:
            self.connect_timeout = connect_timeout
        self._close_client()

    def set_connect_timeout(self, timeout: float):
        self.connect_timeout = timeout
        self._close_client()

    def set_read_timeout(self, timeout: float):
        self.timeout = timeout
        self._close_client()

    def set_ssl_verification(self, verify: bool):
        self.verify_ssl = verify
        self._close_client()

    def set_cache(self, enabled: bool, ttl: float = DEFAULT_CACHE_TTL):
        self.use_cache = enabled
        self.cache_ttl = ttl
        if enabled and not self.cache:
            self.cache = CacheManager(max_item_size=self.cache_max_item_size)
        elif not enabled:
            self.cache = None
        with self._features_lock:
            self._features['cache'] = enabled and self.cache is not None

    def set_retry(self, enabled: bool, total: int = 3, backoff: float = 0.1,
                  status_forcelist: Optional[List[int]] = None):
        if enabled:
            self.retry_total = total
            self.retry_backoff = backoff
            if status_forcelist is not None:
                self.retry_status_forcelist = status_forcelist
        else:
            self.retry_total = 0

    def set_pool_config(self, num_pools: int = DEFAULT_NUM_POOLS, maxsize: int = DEFAULT_POOL_MAXSIZE):
        self.max_connections = maxsize
        self._close_client()

    def set_rate_limit(self, requests_per_second: float, wait_timeout: Optional[float] = None):
        self.rate_limiter.set_rate(requests_per_second)
        with self._features_lock:
            self._features['rate_limit'] = requests_per_second > 0
        if wait_timeout is not None:
            self.rate_limiter.set_wait_timeout(wait_timeout)

    def set_user_agent_rotation(self, enabled: bool, ua_list: Optional[List[str]] = None):
        self.use_random_ua = enabled
        with self._features_lock:
            self._features['ua_rotation'] = enabled
        if ua_list and len(ua_list) > 0:
            self._ua_list = ua_list.copy()
        elif not self._ua_list:
            self._ua_list = self._DEFAULT_UA_LIST.copy()
        with self._ua_lock:
            self._ua_index = 0

    def set_referrer(self, referrer: Optional[str]):
        self.referrer = referrer

    def enable_logging(self, log_dir: str = 'logs', level: int = logging.INFO, console: bool = True):
        logger.configure(enabled=True, log_dir=log_dir, level=level, console=console)

    def disable_logging(self):
        logger.configure(enabled=False)

    @property
    def logging_enabled(self) -> bool:
        return logger.enabled

    def enable_robots_respect(self, user_agent: Optional[str] = None, timeout: Optional[float] = None):
        if user_agent:
            robots_user_agent = user_agent
        else:
            robots_user_agent = self.robots_parser.user_agent if self.robots_parser else 'JWebs/2.0'
        self.respect_robots = True
        with self._features_lock:
            self._features['robots'] = True
        robots_timeout = timeout if timeout is not None else 5.0
        self.robots_parser = RobotsParser(user_agent=robots_user_agent, timeout=robots_timeout)

    def disable_robots_respect(self):
        self.respect_robots = False
        with self._features_lock:
            self._features['robots'] = False
        self.robots_parser = None

    @property
    def robots_enabled(self) -> bool:
        return self._get_feature('robots')

    def set_robots_timeout(self, timeout: float):
        if self.robots_parser:
            self.robots_parser.set_timeout(timeout)

    def set_session_idle_timeout(self, timeout: float):
        self.session_manager.idle_timeout = timeout
        self.session_manager.cleanup_idle_sessions()

    def get_sitemaps(self, url: str) -> List[str]:
        if self.robots_parser:
            return self.robots_parser.get_sitemaps(url)
        return []

    def enable_quick_mode(self):
        with self._quick_mode_lock:
            self.quick_mode = True

    def disable_quick_mode(self):
        with self._quick_mode_lock:
            self.quick_mode = False

    def get_stats(self) -> Dict:
        with self._history_lock:
            total = len(self._history)
            success = len([r for r in self._history if r.status and 200 <= r.status < 400])
            failed = len([r for r in self._history if r.error])
        return {
            'total_requests': total,
            'successful': success,
            'failed': failed,
            'avg_response_time': sum(r.duration for r in self._history) / total if total > 0 else 0,
            'cache_stats': self.cache.get_stats() if self.cache else {},
            'active_sessions': len(self.session_manager.sessions),
            'logging_enabled': self.logging_enabled,
            'robots_respect_enabled': self.robots_enabled,
            'ssl_verification': self.verify_ssl,
            'cache_enabled': self._get_feature('cache'),
            'retry_enabled': self.retry_total > 0,
            'ua_rotation_enabled': self._get_feature('ua_rotation'),
            'referrer_set': self.referrer is not None,
            'connect_timeout': self.connect_timeout,
            'read_timeout': self.timeout,
            'auto_decompress': True,
        }

    def clear_cache(self):
        if self.cache:
            self.cache.clear()

    def clear_history(self):
        with self._history_lock:
            self._history.clear()

    def export_history(self, format: str = 'json', filepath: str = 'history_export') -> str:
        import csv
        with self._history_lock:
            history_list = list(self._history)
        if format == 'json':
            filepath += '.json'
            data = [{'method': r.method, 'url': r.url, 'status': r.status,
                     'duration': r.duration, 'timestamp': r.timestamp, 'error': r.error}
                    for r in history_list]
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        elif format == 'csv':
            filepath += '.csv'
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Method', 'URL', 'Status', 'Duration', 'Timestamp', 'Error'])
                for r in history_list:
                    writer.writerow([r.method, r.url, r.status, r.duration, r.timestamp, r.error])
        return filepath

    def get_last_response(self) -> Optional[HTTPResponse]:
        with self._last_response_lock:
            return self._last_response

    def get_history(self, limit: int = 100) -> List:
        with self._history_lock:
            history_list = list(self._history)
        return history_list[-limit:]

    def _close_client(self):
        with self._lock:
            if self._client:
                self._client.close()
                self._client = None

    def close(self):
        self._close_client()
        if self.cache:
            self.cache._cleanup_db()
        self.session_manager.clear()
