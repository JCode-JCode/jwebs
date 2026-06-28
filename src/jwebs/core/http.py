# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import os
import sys
import json as json_module
import time
import threading
import hashlib
import logging
import warnings
import gzip
import zlib
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Tuple, Set, Callable, Generator, Union
from urllib.parse import urlparse, urljoin

from .exceptions import (
    JWebsError, HTTPError, JWebsConnectionError,
    JWebsTimeoutError, RobotsBlockedError, CacheError
)
from .constants import (
    DEFAULT_CACHE_TTL, DEFAULT_RATE_LIMIT, DEFAULT_RATE_LIMIT_TIMEOUT,
    DEFAULT_SESSION_IDLE_TIMEOUT, DEFAULT_NUM_POOLS, DEFAULT_POOL_MAXSIZE,
    DEFAULT_MAX_WORKERS, DEFAULT_HTTP_TIMEOUT, DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_USER_AGENT, MAX_REDIRECT_HOPS
)
from .datatypes import RequestRecord, CacheEntry
from .logging import logger
from .cache import CacheManager
from .ratelimit import RateLimiter
from .robots import RobotsParser
from .session import SessionManager
from .deps import _check_dep

IS_ANDROID = hasattr(sys, 'getandroidapilevel') or 'ANDROID_STORAGE' in os.environ
IS_IOS = sys.platform == 'ios' or 'IPHONE' in os.environ

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

from urllib3 import PoolManager, ProxyManager, Timeout as Urllib3Timeout, Retry
import ssl


class HTTPResponse:
    __slots__ = (
        'status', 'headers', 'data', 'url', 'error', 'elapsed',
        '_stream', '_raw_response', '_text', '_json', '_encoding', '_closed',
        'auto_decompress'
    )

    def __init__(self, urllib3_response=None, *, status: int = 0, data: bytes = b"",
                 headers: Optional[Dict] = None, url: str = "", error: Optional[str] = None,
                 elapsed: float = 0.0, stream: bool = False, auto_decompress: bool = True):
        self.auto_decompress = auto_decompress
        self._stream = stream
        self._raw_response = None

        if urllib3_response is not None:
            self.status = urllib3_response.status if urllib3_response else 0
            self.headers = dict(urllib3_response.headers) if urllib3_response else {}
            self.url = urllib3_response.geturl() if hasattr(urllib3_response, 'geturl') else ""
            self._raw_response = urllib3_response

            raw_data = urllib3_response.data if urllib3_response else b""

            if auto_decompress and not stream and raw_data:
                content_encoding = self.headers.get('Content-Encoding', '').lower()
                raw_data = self._decompress_body(raw_data, content_encoding)

            if stream:
                self.data = b""
                self._stream = True
            else:
                self.data = raw_data
                self._stream = False
        else:
            self.status = status
            self.data = data if isinstance(data, bytes) else (data.encode('utf-8') if isinstance(data, str) else b"")
            self.headers = headers or {}
            self.url = url
            self._raw_response = None
            self._stream = False

        self.error = error
        self.elapsed = elapsed
        self._text = None
        self._json = None
        self._encoding = None
        self._closed = False

    def _decompress_body(self, data: bytes, encoding: str) -> bytes:
        if not data or not encoding:
            return data
        encoding = encoding.lower()
        try:
            if encoding == 'gzip':
                return gzip.decompress(data)
            elif encoding == 'deflate':
                return zlib.decompress(data, -zlib.MAX_WBITS)
            elif encoding == 'br':
                if HAS_BROTLI:
                    return brotli.decompress(data)
                else:
                    logger.warning('HTTPResponse', 'brotli not installed, cannot decompress br encoding. Install: pip install brotli')
                    return data
        except Exception as e:
            logger.warning('HTTPResponse', f"Decompression failed for {encoding}: {e}")
        return data

    @property
    def stream(self) -> bool:
        return self._stream

    def read(self, amt: Optional[int] = None) -> bytes:
        if not self._stream:
            return self.data
        if self._closed:
            return b""
        if amt is None:
            data = self._raw_response.read()
            self._closed = True
            if self._raw_response:
                self._raw_response.release_conn()
            if self.auto_decompress:
                content_encoding = self.headers.get('Content-Encoding', '').lower()
                data = self._decompress_body(data, content_encoding)
            self.data += data
            return data
        else:
            chunk = self._raw_response.read(amt)
            if self.auto_decompress:
                content_encoding = self.headers.get('Content-Encoding', '').lower()
                chunk = self._decompress_body(chunk, content_encoding)
            self.data += chunk
            if not chunk:
                self._closed = True
                if self._raw_response:
                    self._raw_response.release_conn()
            return chunk

    def iter_content(self, chunk_size: int = 8192) -> Generator[bytes, None, None]:
        if not self._stream:
            yield self.data
            return
        while True:
            chunk = self.read(chunk_size)
            if not chunk:
                break
            yield chunk

    def close(self):
        if self._raw_response and not self._closed:
            self._raw_response.release_conn()
            self._closed = True

    @property
    def text(self) -> str:
        if self._text is not None:
            return self._text
        if self._stream and not self._closed:
            self.read()
        if not self.data:
            self._text = ""
            return self._text
        encoding = self._detect_encoding()
        try:
            self._text = self.data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            for enc in ['utf-8', 'latin-1', 'windows-1256', 'cp1252', 'iso-8859-1']:
                try:
                    self._text = self.data.decode(enc, errors='replace')
                    self._encoding = enc
                    return self._text
                except (UnicodeDecodeError, LookupError):
                    continue
            self._text = self.data.decode('utf-8', errors='replace')
            self._encoding = 'utf-8'
        return self._text

    @text.setter
    def text(self, value: str):
        self._text = value

    @property
    def encoding(self) -> str:
        if self._encoding is None:
            self._detect_encoding()
        return self._encoding or 'utf-8'

    def _detect_encoding(self) -> str:
        import re
        content_type = self.headers.get('Content-Type', '') or self.headers.get('content-type', '')
        if 'charset=' in content_type.lower():
            charset = content_type.lower().split('charset=')[-1].split(';')[0].strip()
            if charset:
                self._encoding = charset
                return charset
        try:
            sample = self.data[:2000]
            if b'<html' in sample.lower() or b'<!doctype' in sample.lower():
                patterns = [
                    rb'<meta[^>]*charset=["\']?\s*([^"\'\s;>]+)',
                    rb'<meta[^>]*charset\s*=\s*([^"\'\s;>]+)',
                ]
                for pattern in patterns:
                    match = re.search(pattern, sample, re.IGNORECASE)
                    if match:
                        charset = match.group(1).decode('ascii', errors='ignore')
                        self._encoding = charset
                        return charset
        except Exception:
            pass
        if self.data.startswith(b'\xef\xbb\xbf'):
            self._encoding = 'utf-8-sig'
            return 'utf-8-sig'
        elif self.data.startswith(b'\xff\xfe'):
            self._encoding = 'utf-16-le'
            return 'utf-16-le'
        elif self.data.startswith(b'\xfe\xff'):
            self._encoding = 'utf-16-be'
            return 'utf-16-be'
        if _check_dep('chardet'):
            try:
                import chardet
                detected = chardet.detect(self.data[:10000])
                if detected and detected.get('confidence', 0) > 0.7:
                    self._encoding = detected['encoding']
                    return detected['encoding']
            except Exception:
                pass
        if _check_dep('charset_normalizer'):
            try:
                from charset_normalizer import from_bytes as charset_from_bytes
                results = charset_from_bytes(self.data[:10000])
                if results:
                    best = results.best()
                    if best:
                        self._encoding = best.encoding
                        return best.encoding
            except Exception:
                pass
        self._encoding = 'utf-8'
        return 'utf-8'

    def JSON(self) -> Optional[Any]:
        if self._json is not None:
            return self._json
        try:
            self._json = json_module.loads(self.text)
            return self._json
        except (json_module.JSONDecodeError, ValueError):
            return None

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400

    @property
    def is_redirect(self) -> bool:
        return self.status in (301, 302, 303, 307, 308)

    @property
    def is_client_error(self) -> bool:
        return 400 <= self.status < 500

    @property
    def is_server_error(self) -> bool:
        return 500 <= self.status < 600

    def raise_for_status(self):
        if self.error:
            raise HTTPError(f"Request failed: {self.error}", url=self.url)
        if self.is_client_error or self.is_server_error:
            raise HTTPError(
                f"{self.status} error for URL: {self.url}",
                status_code=self.status,
                url=self.url,
                response=self
            )

    def __repr__(self) -> str:
        if self.error:
            return f"<HTTPResponse [ERROR] {self.url} - {self.error}>"
        return f"<HTTPResponse [{self.status}] {self.url}>"

    def __bool__(self) -> bool:
        return self.error is None and self.status is not None and self.status >= 200

    def __del__(self):
        self.close()


class FastHTTP:
    _DEFAULT_UA_LIST = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Android 14; Mobile; rv:125.0) Gecko/125.0 Firefox/125.0',
    ]

    def __init__(self, num_pools: int = DEFAULT_NUM_POOLS,
                 default_headers: Optional[Dict] = None,
                 timeout: Optional[float] = DEFAULT_HTTP_TIMEOUT,
                 connect_timeout: Optional[float] = DEFAULT_CONNECT_TIMEOUT,
                 use_cache: bool = False,
                 cache_ttl: float = DEFAULT_CACHE_TTL,
                 cache_max_item_size: Optional[int] = 5 * 1024 * 1024,
                 rate_limit: float = DEFAULT_RATE_LIMIT,
                 rate_limit_timeout: float = DEFAULT_RATE_LIMIT_TIMEOUT,
                 max_workers: int = DEFAULT_MAX_WORKERS,
                 use_random_ua: bool = False,
                 ua_list: Optional[List[str]] = None,
                 referrer: Optional[str] = None,
                 enable_logging: bool = False,
                 log_dir: str = 'logs',
                 log_level: int = logging.INFO,
                 log_console: bool = True,
                 respect_robots_txt: bool = False,
                 robots_user_agent: str = 'JWebs/2.0',
                 robots_timeout: float = 5.0,
                 verify_ssl: bool = True,
                 use_retry: bool = False,
                 retry_total: int = 3,
                 retry_backoff: float = 0.1,
                 retry_status_forcelist: Optional[List[int]] = None,
                 pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
                 session_idle_timeout: float = DEFAULT_SESSION_IDLE_TIMEOUT,
                 allow_expired_sessions: bool = False,
                 suppress_ssl_warnings: bool = True,
                 auto_decompress: bool = True,
                 redirects: Union[bool, int] = False,
                 use_proxy: bool = False,
                 proxy_rotator: Optional[Any] = None,
                 client_cert: Optional[str] = None,
                 client_key: Optional[str] = None,
                 client_cert_password: Optional[str] = None,
                 ca_bundle: Optional[str] = None):

        logger.configure(enabled=enable_logging, log_dir=log_dir,
                         level=log_level, console=log_console)

        if suppress_ssl_warnings:
            from urllib3 import disable_warnings
            from urllib3.exceptions import InsecureRequestWarning
            disable_warnings(InsecureRequestWarning)

        self.num_pools = num_pools
        self.pool_maxsize = pool_maxsize
        self.connect_timeout = connect_timeout
        self.read_timeout = timeout
        self.auto_decompress = auto_decompress
        self.verify_ssl = verify_ssl
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self.cache_max_item_size = cache_max_item_size
        self.use_retry = use_retry
        self.retry_total = retry_total
        self.retry_backoff = retry_backoff
        self.retry_status_forcelist = retry_status_forcelist or [429, 500, 502, 503, 504]

        self.default_headers = default_headers or {
            'User-Agent': self._DEFAULT_UA_LIST[0],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        self.cache = CacheManager(max_item_size=cache_max_item_size) if use_cache else None
        self.rate_limiter = RateLimiter(rate_limit, rate_limit_timeout)
        self.session_manager = SessionManager(session_idle_timeout)
        self.max_workers = max_workers

        self.use_random_ua = use_random_ua
        self._ua_list = ua_list if ua_list and len(ua_list) > 0 else self._DEFAULT_UA_LIST.copy()
        self._ua_index = 0
        self._ua_lock = threading.Lock()

        self.referrer = referrer

        self.respect_robots = respect_robots_txt
        self._robots_user_agent = robots_user_agent
        self.robots_parser = RobotsParser(user_agent=robots_user_agent,
                                          timeout=robots_timeout) if respect_robots_txt else None

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

        self.redirects = redirects

        self.use_proxy = use_proxy
        self.proxy_rotator = proxy_rotator
        self._proxy_managers: Dict[tuple, Any] = {}
        self._last_proxy_key = None
        self._last_proxy_manager = None

        self.default_client_cert = client_cert
        self.default_client_key = client_key
        self.default_client_cert_password = client_cert_password
        self.default_ca_bundle = ca_bundle

        self._pool: Optional[PoolManager] = None
        self._pool_lock = threading.Lock()
        self._init_pool()

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
        self.allow_expired_sessions = allow_expired_sessions

    def _get_feature(self, name: str) -> bool:
        with self._features_lock:
            return self._features.get(name, False)

    def _get_next_ua(self) -> str:
        if not self._get_feature('ua_rotation'):
            return self.default_headers.get('User-Agent', self._DEFAULT_UA_LIST[0])
        with self._ua_lock:
            ua = self._ua_list[self._ua_index]
            self._ua_index = (self._ua_index + 1) % len(self._ua_list)
            return ua

    def _build_headers(self, headers: Optional[Dict] = None,
                       session_id: Optional[str] = None) -> Dict:
        final_headers = {
            **self.default_headers,
            'User-Agent': self._get_next_ua(),
            **(headers or {})
        }
        if self.referrer:
            final_headers['Referer'] = self.referrer

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
                logger.error('FastHTTP', f"Hook '{hook_type}' failed: {e}", exc_info=True)

    def _record_request(self, record: RequestRecord):
        if not self._get_feature('history'):
            return
        with self._history_lock:
            self._history.append(record)

    def _create_ssl_context(self, client_cert=None, client_key=None, client_cert_password=None, ca_bundle=None):
        ctx = None
        if client_cert or ca_bundle or not self.verify_ssl:
            ctx = ssl.create_default_context(
                cafile=ca_bundle if ca_bundle else (self.default_ca_bundle if self.default_ca_bundle else None)
            )
            if self.verify_ssl:
                ctx.verify_mode = ssl.CERT_REQUIRED
            else:
                ctx.verify_mode = ssl.CERT_NONE
            cert_file = client_cert if client_cert is not None else self.default_client_cert
            key_file = client_key if client_key is not None else self.default_client_key
            password = client_cert_password if client_cert_password is not None else self.default_client_cert_password
            if cert_file:
                ctx.load_cert_chain(cert_file, keyfile=key_file, password=password)
        return ctx

    def _init_pool(self):
        with self._pool_lock:
            retry_config = None
            if self.use_retry:
                retry_config = Retry(
                    total=self.retry_total,
                    read=self.retry_total,
                    connect=self.retry_total,
                    backoff_factor=self.retry_backoff,
                    status_forcelist=self.retry_status_forcelist
                )

            ssl_context = self._create_ssl_context()
            if ssl_context:
                self._pool = PoolManager(
                    num_pools=self.num_pools,
                    maxsize=self.pool_maxsize,
                    block=False,
                    headers=self.default_headers,
                    timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout),
                    retries=retry_config if retry_config else False,
                    ssl_context=ssl_context
                )
            else:
                self._pool = PoolManager(
                    num_pools=self.num_pools,
                    maxsize=self.pool_maxsize,
                    block=False,
                    headers=self.default_headers,
                    timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout),
                    retries=retry_config if retry_config else False,
                    cert_reqs='CERT_REQUIRED' if self.verify_ssl else 'CERT_NONE',
                    ca_certs=self.default_ca_bundle,
                    cert_file=self.default_client_cert,
                    key_file=self.default_client_key
                )

    def _get_proxy_manager(self, proxy_url: str, client_cert=None, client_key=None,
                           client_cert_password=None, ca_bundle=None):
        key = (proxy_url, client_cert, client_key, ca_bundle)
        if self._last_proxy_manager is not None and self._last_proxy_key != key:
            self._last_proxy_manager.clear()
            self._last_proxy_manager = None
        if key not in self._proxy_managers:
            retry_config = None
            if self.use_retry:
                retry_config = Retry(
                    total=self.retry_total,
                    read=self.retry_total,
                    connect=self.retry_total,
                    backoff_factor=self.retry_backoff,
                    status_forcelist=self.retry_status_forcelist
                )

            ssl_context = self._create_ssl_context(client_cert, client_key, client_cert_password, ca_bundle)
            if ssl_context:
                self._proxy_managers[key] = ProxyManager(
                    proxy_url=proxy_url,
                    num_pools=self.num_pools,
                    maxsize=self.pool_maxsize,
                    block=False,
                    headers=self.default_headers,
                    timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout),
                    retries=retry_config if retry_config else False,
                    ssl_context=ssl_context
                )
            else:
                self._proxy_managers[key] = ProxyManager(
                    proxy_url=proxy_url,
                    num_pools=self.num_pools,
                    maxsize=self.pool_maxsize,
                    block=False,
                    headers=self.default_headers,
                    timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout),
                    retries=retry_config if retry_config else False,
                    cert_reqs='CERT_REQUIRED' if self.verify_ssl else 'CERT_NONE',
                    ca_certs=ca_bundle if ca_bundle else self.default_ca_bundle,
                    cert_file=client_cert if client_cert is not None else self.default_client_cert,
                    key_file=client_key if client_key is not None else self.default_client_key
                )
        self._last_proxy_key = key
        self._last_proxy_manager = self._proxy_managers[key]
        return self._proxy_managers[key]

    def _quick_request(self, method: str, url: str, headers: Optional[Dict] = None,
                       body: Optional[Any] = None, fields: Optional[Dict] = None,
                       json: Optional[Any] = None, timeout: Optional[float] = None,
                       connect_timeout: Optional[float] = None,
                       redirects: Optional[Union[bool, int]] = None,
                       preload_content: bool = True,
                       raise_on_error: bool = True,
                       proxies: Optional[Dict] = None,
                       timeouts: Optional[Union[float, Tuple[float, float]]] = None,
                       client_cert: Optional[str] = None,
                       client_key: Optional[str] = None,
                       client_cert_password: Optional[str] = None,
                       ca_bundle: Optional[str] = None) -> HTTPResponse:
        start = time.monotonic()

        if timeouts is not None:
            if isinstance(timeouts, (int, float)):
                effective_connect = timeouts
                effective_read = timeouts
            elif isinstance(timeouts, tuple) and len(timeouts) == 2:
                effective_connect, effective_read = timeouts
            else:
                raise TypeError("timeouts must be a number or a tuple of two numbers")
        else:
            effective_connect = connect_timeout if connect_timeout is not None else self.connect_timeout
            effective_read = timeout if timeout is not None else self.read_timeout

        use_redirects = self.redirects if redirects is None else redirects

        proxy_url = None
        if proxies:
            proxy_url = proxies.get('https') or proxies.get('http')
        elif self.use_proxy and self.proxy_rotator:
            proxy_config = self.proxy_rotator.GET_PROXY()
            if proxy_config:
                proxy_url = proxy_config.get('http')
        if proxy_url:
            manager = self._get_proxy_manager(proxy_url, client_cert, client_key, client_cert_password, ca_bundle)
        else:
            manager = self._pool

        try:
            final_headers = self.default_headers.copy()
            if headers:
                final_headers.update(headers)
            if json is not None:
                body = json_module.dumps(json, ensure_ascii=False).encode('utf-8')
                final_headers['Content-Type'] = 'application/json; charset=utf-8'

            pool_timeout = Urllib3Timeout(connect=effective_connect, read=effective_read)

            current_url = url
            current_method = method
            current_body = body
            current_fields = fields
            current_headers = final_headers
            max_hops = 30 if use_redirects is True else (use_redirects if isinstance(use_redirects, int) and use_redirects > 0 else 0)

            for hop in range(max_hops + 1):
                if current_method in ('GET', 'HEAD', 'OPTIONS', 'DELETE'):
                    resp = manager.request(
                        current_method, current_url, headers=current_headers,
                        redirect=False,
                        preload_content=preload_content,
                        timeout=pool_timeout
                    )
                elif current_method == 'POST' and current_fields:
                    resp = manager.request(
                        'POST', current_url, headers=current_headers,
                        fields=current_fields, encode_multipart=True,
                        redirect=False,
                        timeout=pool_timeout
                    )
                else:
                    resp = manager.request(
                        current_method, current_url, headers=current_headers,
                        body=current_body, fields=current_fields,
                        redirect=False,
                        timeout=pool_timeout
                    )

                if resp.status in (301, 302, 303, 307, 308) and max_hops > 0 and hop < max_hops:
                    location = resp.headers.get('Location')
                    if not location:
                        break
                    current_url = urljoin(current_url, location)
                    if resp.status in (301, 302, 303):
                        current_method = 'GET'
                        current_body = None
                        current_fields = None
                        current_headers.pop('Content-Type', None)
                        current_headers.pop('Content-Length', None)
                    resp.release_conn()
                    continue
                else:
                    wrapped = HTTPResponse(resp, stream=False, auto_decompress=self.auto_decompress)
                    wrapped.url = current_url
                    wrapped.elapsed = time.monotonic() - start
                    if resp is not None:
                        resp.release_conn()
                    if raise_on_error and (wrapped.is_client_error or wrapped.is_server_error):
                        wrapped.raise_for_status()
                    return wrapped

            wrapped = HTTPResponse(resp, stream=False, auto_decompress=self.auto_decompress)
            wrapped.url = current_url
            wrapped.elapsed = time.monotonic() - start
            return wrapped

        except (HTTPError, RobotsBlockedError):
            raise
        except Exception as e:
            err_msg = str(e)
            if raise_on_error:
                raise JWebsError(err_msg) from e
            return HTTPResponse(status=0, url=url, error=err_msg,
                                elapsed=time.monotonic() - start, auto_decompress=self.auto_decompress)

    def _do_request(self, method: str, url: str, headers: Optional[Dict] = None,
                    body: Optional[Any] = None, fields: Optional[Dict] = None,
                    json: Optional[Any] = None, timeout: Optional[float] = None,
                    connect_timeout: Optional[float] = None,
                    session_id: Optional[str] = None, stream: bool = False,
                    multipart: bool = False, respect_robots: Optional[bool] = None,
                    redirects: Optional[Union[bool, int]] = None,
                    preload_content: bool = True,
                    raise_on_error: bool = False,
                    auto_decompress: Optional[bool] = None,
                    proxies: Optional[Dict] = None,
                    timeouts: Optional[Union[float, Tuple[float, float]]] = None,
                    client_cert: Optional[str] = None,
                    client_key: Optional[str] = None,
                    client_cert_password: Optional[str] = None,
                    ca_bundle: Optional[str] = None) -> HTTPResponse:

        use_decompress = auto_decompress if auto_decompress is not None else self.auto_decompress

        with self._quick_mode_lock:
            if self.quick_mode:
                return self._quick_request(
                    method=method, url=url, headers=headers, body=body, fields=fields,
                    json=json, timeout=timeout, connect_timeout=connect_timeout,
                    redirects=redirects,
                    preload_content=preload_content, raise_on_error=raise_on_error,
                    proxies=proxies, timeouts=timeouts,
                    client_cert=client_cert, client_key=client_key,
                    client_cert_password=client_cert_password, ca_bundle=ca_bundle
                )

        should_check = respect_robots if respect_robots is not None else self._get_feature('robots')
        if should_check and self.robots_parser:
            if not self.robots_parser.is_allowed(url):
                if self._get_feature('hooks'):
                    self._execute_hooks('on_blocked', method=method, url=url, reason='robots.txt')
                err_msg = f"Blocked by robots.txt: {url}"
                logger.warning('FastHTTP', err_msg)
                if raise_on_error:
                    raise RobotsBlockedError(url)
                return HTTPResponse(status=0, url=url, error=err_msg, auto_decompress=use_decompress)
            crawl_delay = self.robots_parser.get_crawl_delay(url)
            if crawl_delay and crawl_delay > 0:
                time.sleep(crawl_delay)

        if self._get_feature('rate_limit') and self.rate_limiter:
            if not self.rate_limiter.wait_and_acquire():
                err_msg = f"Rate limit timeout for URL: {url}"
                logger.error('FastHTTP', err_msg)
                if raise_on_error:
                    raise JWebsTimeoutError(err_msg)
                return HTTPResponse(status=0, url=url, error=err_msg, auto_decompress=use_decompress)

        if self._get_feature('hooks'):
            self._execute_hooks('before_request', method=method, url=url)

        start_time = time.monotonic()
        record = RequestRecord(method=method, url=url) if self._get_feature('history') else None

        use_redirects = self.redirects if redirects is None else redirects

        if timeouts is not None:
            if isinstance(timeouts, (int, float)):
                effective_connect = timeouts
                effective_read = timeouts
            elif isinstance(timeouts, tuple) and len(timeouts) == 2:
                effective_connect, effective_read = timeouts
            else:
                raise TypeError("timeouts must be a number or a tuple of two numbers")
        else:
            effective_connect = connect_timeout if connect_timeout is not None else self.connect_timeout
            effective_read = timeout if timeout is not None else self.read_timeout

        proxy_url = None
        if proxies:
            proxy_url = proxies.get('https') or proxies.get('http')
        elif self.use_proxy and self.proxy_rotator:
            proxy_config = self.proxy_rotator.GET_PROXY()
            if proxy_config:
                proxy_url = proxy_config.get('http')
        if proxy_url:
            manager = self._get_proxy_manager(proxy_url, client_cert, client_key, client_cert_password, ca_bundle)
        else:
            if (client_cert is not None and client_cert != self.default_client_cert) or \
               (ca_bundle is not None and ca_bundle != self.default_ca_bundle):
                retry_config = None
                if self.use_retry:
                    retry_config = Retry(
                        total=self.retry_total,
                        read=self.retry_total,
                        connect=self.retry_total,
                        backoff_factor=self.retry_backoff,
                        status_forcelist=self.retry_status_forcelist
                    )
                ssl_context = self._create_ssl_context(client_cert, client_key, client_cert_password, ca_bundle)
                if ssl_context:
                    manager = PoolManager(
                        num_pools=1,
                        maxsize=1,
                        block=False,
                        headers=self.default_headers,
                        timeout=Urllib3Timeout(connect=effective_connect, read=effective_read),
                        retries=retry_config if retry_config else False,
                        ssl_context=ssl_context
                    )
                else:
                    manager = PoolManager(
                        num_pools=1,
                        maxsize=1,
                        block=False,
                        headers=self.default_headers,
                        timeout=Urllib3Timeout(connect=effective_connect, read=effective_read),
                        retries=retry_config if retry_config else False,
                        cert_reqs='CERT_REQUIRED' if self.verify_ssl else 'CERT_NONE',
                        ca_certs=ca_bundle if ca_bundle else self.default_ca_bundle,
                        cert_file=client_cert if client_cert is not None else self.default_client_cert,
                        key_file=client_key if client_key is not None else self.default_client_key
                    )
            else:
                manager = self._pool

        try:
            final_headers = self._build_headers(headers, session_id)
            if json is not None:
                body = json_module.dumps(json, ensure_ascii=False).encode('utf-8')
                final_headers['Content-Type'] = 'application/json; charset=utf-8'

            pool_timeout = Urllib3Timeout(connect=effective_connect, read=effective_read)

            current_url = url
            current_method = method
            current_body = body
            current_fields = fields
            current_headers = final_headers
            max_hops = 30 if use_redirects is True else (use_redirects if isinstance(use_redirects, int) and use_redirects > 0 else 0)
            last_response = None

            for hop in range(max_hops + 1):
                if current_method in ('GET', 'HEAD', 'OPTIONS', 'DELETE'):
                    resp = manager.request(
                        current_method, current_url, headers=current_headers,
                        redirect=False,
                        preload_content=preload_content,
                        timeout=pool_timeout
                    )
                elif current_method == 'POST' and multipart and current_fields:
                    resp = manager.request(
                        'POST', current_url, headers=current_headers,
                        fields=current_fields, encode_multipart=True,
                        redirect=False,
                        timeout=pool_timeout
                    )
                else:
                    resp = manager.request(
                        current_method, current_url, headers=current_headers,
                        body=current_body, fields=current_fields,
                        redirect=False,
                        timeout=pool_timeout
                    )

                if resp.status in (301, 302, 303, 307, 308) and max_hops > 0 and hop < max_hops:
                    location = resp.headers.get('Location')
                    if not location:
                        last_response = resp
                        break
                    current_url = urljoin(current_url, location)
                    if resp.status in (301, 302, 303):
                        current_method = 'GET'
                        current_body = None
                        current_fields = None
                        current_headers.pop('Content-Type', None)
                        current_headers.pop('Content-Length', None)
                    resp.release_conn()
                    continue
                else:
                    last_response = resp
                    break

            if last_response is None:
                raise JWebsError("No response received during redirect handling")

            duration = time.monotonic() - start_time

            if record is not None:
                record.status = last_response.status
                record.duration = duration
                record.headers_received = dict(last_response.headers)
                record.content_type = last_response.headers.get('Content-Type', '')
                try:
                    record.content_length = int(last_response.headers.get('Content-Length', 0))
                except (ValueError, TypeError):
                    record.content_length = 0
                self._record_request(record)

            is_stream = stream and not preload_content
            wrapped = HTTPResponse(last_response, stream=is_stream, auto_decompress=use_decompress)
            wrapped.url = current_url
            wrapped.elapsed = duration
            with self._last_response_lock:
                self._last_response = wrapped

            if not is_stream and last_response is not None:
                last_response.release_conn()

            if session_id and self._get_feature('session'):
                self.session_manager.update_from_response(session_id, dict(last_response.headers))

            if self._get_feature('cache') and self.cache and last_response.status == 200 and not is_stream:
                ttl = self._get_cache_ttl(last_response.headers)
                self.cache.set(
                    url, wrapped.data, ttl=ttl,
                    etag=last_response.headers.get('ETag'),
                    last_modified=last_response.headers.get('Last-Modified')
                )

            if self._get_feature('hooks'):
                self._execute_hooks('after_request', method=method, url=url,
                                    response=wrapped, duration=duration)

            if raise_on_error and (wrapped.is_client_error or wrapped.is_server_error):
                wrapped.raise_for_status()

            return wrapped

        except (RobotsBlockedError, HTTPError):
            raise
        except Exception as e:
            if record:
                record.error = str(e)
                self._record_request(record)
            logger.error('FastHTTP', f"{method} FAILED: {url} - {e}", exc_info=True)
            if self._get_feature('hooks'):
                self._execute_hooks('on_error', method=method, url=url, error=e)
            err_msg = str(e)
            if raise_on_error:
                raise JWebsError(err_msg) from e
            return HTTPResponse(status=0, url=url, error=err_msg, auto_decompress=use_decompress)

    def _get_cache_ttl(self, headers: Dict) -> float:
        cache_control = headers.get('Cache-Control', '') or headers.get('cache-control', '')
        if 'max-age=' in cache_control:
            try:
                return float(cache_control.split('max-age=')[1].split(',')[0])
            except (ValueError, IndexError):
                pass
        return self.cache_ttl

    def GET(self, url: str, headers: Optional[Dict] = None, timeout: Optional[float] = None,
            connect_timeout: Optional[float] = None,
            session_id: Optional[str] = None, respect_robots: Optional[bool] = None,
            stream: bool = False, raise_on_error: bool = False,
            auto_decompress: Optional[bool] = None,
            redirects: Optional[Union[bool, int]] = None,
            proxies: Optional[Dict] = None,
            timeouts: Optional[Union[float, Tuple[float, float]]] = None,
            client_cert: Optional[str] = None,
            client_key: Optional[str] = None,
            client_cert_password: Optional[str] = None,
            ca_bundle: Optional[str] = None) -> HTTPResponse:
        if self._get_feature('cache') and self.cache and not stream and not self.quick_mode:
            cached = self.cache.get(url)
            if cached is not None:
                if isinstance(cached, bytes):
                    return HTTPResponse(status=200, data=cached, url=url, headers={}, auto_decompress=auto_decompress if auto_decompress is not None else self.auto_decompress)
                return HTTPResponse(status=200, data=str(cached), url=url, headers={}, auto_decompress=auto_decompress if auto_decompress is not None else self.auto_decompress)
        return self._do_request(
            'GET', url, headers=headers, timeout=timeout,
            connect_timeout=connect_timeout,
            session_id=session_id, stream=stream,
            respect_robots=respect_robots,
            preload_content=not stream,
            raise_on_error=raise_on_error,
            auto_decompress=auto_decompress,
            redirects=redirects,
            proxies=proxies,
            timeouts=timeouts,
            client_cert=client_cert, client_key=client_key,
            client_cert_password=client_cert_password, ca_bundle=ca_bundle
        )

    def POST(self, url: str, headers: Optional[Dict] = None, body: Optional[Any] = None,
             fields: Optional[Dict] = None, json: Optional[Any] = None,
             timeout: Optional[float] = None, connect_timeout: Optional[float] = None,
             session_id: Optional[str] = None,
             multipart: bool = False, respect_robots: Optional[bool] = None,
             raise_on_error: bool = False,
             auto_decompress: Optional[bool] = None,
             redirects: Optional[Union[bool, int]] = None,
             proxies: Optional[Dict] = None,
             timeouts: Optional[Union[float, Tuple[float, float]]] = None,
             client_cert: Optional[str] = None,
             client_key: Optional[str] = None,
             client_cert_password: Optional[str] = None,
             ca_bundle: Optional[str] = None) -> HTTPResponse:
        return self._do_request(
            'POST', url, headers=headers, body=body, fields=fields,
            json=json, timeout=timeout,
            connect_timeout=connect_timeout,
            session_id=session_id,
            multipart=multipart, respect_robots=respect_robots,
            raise_on_error=raise_on_error,
            auto_decompress=auto_decompress,
            redirects=redirects,
            proxies=proxies,
            timeouts=timeouts,
            client_cert=client_cert, client_key=client_key,
            client_cert_password=client_cert_password, ca_bundle=ca_bundle
        )

    def PUT(self, url: str, headers: Optional[Dict] = None, body: Optional[Any] = None,
            fields: Optional[Dict] = None, json: Optional[Any] = None,
            timeout: Optional[float] = None, connect_timeout: Optional[float] = None,
            session_id: Optional[str] = None,
            raise_on_error: bool = False,
            auto_decompress: Optional[bool] = None,
            redirects: Optional[Union[bool, int]] = None,
            proxies: Optional[Dict] = None,
            timeouts: Optional[Union[float, Tuple[float, float]]] = None,
            client_cert: Optional[str] = None,
            client_key: Optional[str] = None,
            client_cert_password: Optional[str] = None,
            ca_bundle: Optional[str] = None) -> HTTPResponse:
        return self._do_request(
            'PUT', url, headers=headers, body=body, fields=fields,
            json=json, timeout=timeout,
            connect_timeout=connect_timeout,
            session_id=session_id,
            raise_on_error=raise_on_error,
            auto_decompress=auto_decompress,
            redirects=redirects,
            proxies=proxies,
            timeouts=timeouts,
            client_cert=client_cert, client_key=client_key,
            client_cert_password=client_cert_password, ca_bundle=ca_bundle
        )

    def PATCH(self, url: str, headers: Optional[Dict] = None, body: Optional[Any] = None,
              fields: Optional[Dict] = None, json: Optional[Any] = None,
              timeout: Optional[float] = None, connect_timeout: Optional[float] = None,
              session_id: Optional[str] = None,
              raise_on_error: bool = False,
              auto_decompress: Optional[bool] = None,
              redirects: Optional[Union[bool, int]] = None,
              proxies: Optional[Dict] = None,
              timeouts: Optional[Union[float, Tuple[float, float]]] = None,
              client_cert: Optional[str] = None,
              client_key: Optional[str] = None,
              client_cert_password: Optional[str] = None,
              ca_bundle: Optional[str] = None) -> HTTPResponse:
        return self._do_request(
            'PATCH', url, headers=headers, body=body, fields=fields,
            json=json, timeout=timeout,
            connect_timeout=connect_timeout,
            session_id=session_id,
            raise_on_error=raise_on_error,
            auto_decompress=auto_decompress,
            redirects=redirects,
            proxies=proxies,
            timeouts=timeouts,
            client_cert=client_cert, client_key=client_key,
            client_cert_password=client_cert_password, ca_bundle=ca_bundle
        )

    def DELETE(self, url: str, headers: Optional[Dict] = None,
               timeout: Optional[float] = None, connect_timeout: Optional[float] = None,
               session_id: Optional[str] = None,
               raise_on_error: bool = False,
               auto_decompress: Optional[bool] = None,
               redirects: Optional[Union[bool, int]] = None,
               proxies: Optional[Dict] = None,
               timeouts: Optional[Union[float, Tuple[float, float]]] = None,
               client_cert: Optional[str] = None,
               client_key: Optional[str] = None,
               client_cert_password: Optional[str] = None,
               ca_bundle: Optional[str] = None) -> HTTPResponse:
        return self._do_request(
            'DELETE', url, headers=headers, timeout=timeout,
            connect_timeout=connect_timeout,
            session_id=session_id, raise_on_error=raise_on_error,
            auto_decompress=auto_decompress,
            redirects=redirects,
            proxies=proxies,
            timeouts=timeouts,
            client_cert=client_cert, client_key=client_key,
            client_cert_password=client_cert_password, ca_bundle=ca_bundle
        )

    def HEAD(self, url: str, headers: Optional[Dict] = None,
             timeout: Optional[float] = None, connect_timeout: Optional[float] = None,
             session_id: Optional[str] = None,
             raise_on_error: bool = False,
             auto_decompress: Optional[bool] = None,
             redirects: Optional[Union[bool, int]] = None,
             proxies: Optional[Dict] = None,
             timeouts: Optional[Union[float, Tuple[float, float]]] = None,
             client_cert: Optional[str] = None,
             client_key: Optional[str] = None,
             client_cert_password: Optional[str] = None,
             ca_bundle: Optional[str] = None) -> HTTPResponse:
        return self._do_request(
            'HEAD', url, headers=headers, timeout=timeout,
            connect_timeout=connect_timeout,
            session_id=session_id, preload_content=False,
            raise_on_error=raise_on_error,
            auto_decompress=auto_decompress,
            redirects=redirects,
            proxies=proxies,
            timeouts=timeouts,
            client_cert=client_cert, client_key=client_key,
            client_cert_password=client_cert_password, ca_bundle=ca_bundle
        )

    def OPTIONS(self, url: str, headers: Optional[Dict] = None,
                timeout: Optional[float] = None, connect_timeout: Optional[float] = None,
                session_id: Optional[str] = None,
                raise_on_error: bool = False,
                auto_decompress: Optional[bool] = None,
                redirects: Optional[Union[bool, int]] = None,
                proxies: Optional[Dict] = None,
                timeouts: Optional[Union[float, Tuple[float, float]]] = None,
                client_cert: Optional[str] = None,
                client_key: Optional[str] = None,
                client_cert_password: Optional[str] = None,
                ca_bundle: Optional[str] = None) -> HTTPResponse:
        return self._do_request(
            'OPTIONS', url, headers=headers, timeout=timeout,
            connect_timeout=connect_timeout,
            session_id=session_id, raise_on_error=raise_on_error,
            auto_decompress=auto_decompress,
            redirects=redirects,
            proxies=proxies,
            timeouts=timeouts,
            client_cert=client_cert, client_key=client_key,
            client_cert_password=client_cert_password, ca_bundle=ca_bundle
        )

    def BATCH(self, urls: List[str], method: str = 'GET', max_workers: Optional[int] = None,
              raise_on_error: bool = False, auto_decompress: Optional[bool] = None,
              redirects: Optional[Union[bool, int]] = None,
              proxies: Optional[Dict] = None,
              timeouts: Optional[Union[float, Tuple[float, float]]] = None,
              client_cert: Optional[str] = None,
              client_key: Optional[str] = None,
              client_cert_password: Optional[str] = None,
              ca_bundle: Optional[str] = None,
              **kwargs) -> Dict[str, Any]:
        max_workers = max_workers or self.max_workers
        results = {}
        method_func = getattr(self, method.upper(), self.GET)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(method_func, url, raise_on_error=False,
                                auto_decompress=auto_decompress,
                                redirects=redirects,
                                proxies=proxies,
                                timeouts=timeouts,
                                client_cert=client_cert, client_key=client_key,
                                client_cert_password=client_cert_password, ca_bundle=ca_bundle,
                                **kwargs): url
                for url in urls
            }
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    logger.error('FastHTTP', f"Batch result error for {url}: {e}", exc_info=True)
                    if raise_on_error:
                        raise
                    results[url] = HTTPResponse(status=0, url=url, error=str(e), auto_decompress=auto_decompress if auto_decompress is not None else self.auto_decompress)
        return results

    def TEXT(self, url: str, raise_on_error: bool = True, auto_decompress: Optional[bool] = None,
             redirects: Optional[Union[bool, int]] = None,
             proxies: Optional[Dict] = None,
             timeouts: Optional[Union[float, Tuple[float, float]]] = None,
             client_cert: Optional[str] = None,
             client_key: Optional[str] = None,
             client_cert_password: Optional[str] = None,
             ca_bundle: Optional[str] = None,
             **kwargs) -> Optional[str]:
        resp = self.GET(url, raise_on_error=raise_on_error, auto_decompress=auto_decompress,
                        redirects=redirects, proxies=proxies, timeouts=timeouts,
                        client_cert=client_cert, client_key=client_key,
                        client_cert_password=client_cert_password, ca_bundle=ca_bundle,
                        **kwargs)
        if resp and resp.status > 0:
            return resp.text
        if raise_on_error:
            raise JWebsConnectionError(f"Failed to get text from {url}: {resp.error if resp else 'No response'}")
        return None

    def JSON(self, url: str, raise_on_error: bool = True, auto_decompress: Optional[bool] = None,
             redirects: Optional[Union[bool, int]] = None,
             proxies: Optional[Dict] = None,
             timeouts: Optional[Union[float, Tuple[float, float]]] = None,
             client_cert: Optional[str] = None,
             client_key: Optional[str] = None,
             client_cert_password: Optional[str] = None,
             ca_bundle: Optional[str] = None,
             **kwargs) -> Optional[Any]:
        resp = self.GET(url, raise_on_error=raise_on_error, auto_decompress=auto_decompress,
                        redirects=redirects, proxies=proxies, timeouts=timeouts,
                        client_cert=client_cert, client_key=client_key,
                        client_cert_password=client_cert_password, ca_bundle=ca_bundle,
                        **kwargs)
        if resp and resp.status > 0:
            data = resp.JSON()
            if data is not None:
                return data
            if raise_on_error:
                raise ValueError(f"Invalid JSON response from {url}")
            return None
        if raise_on_error:
            raise JWebsConnectionError(f"Failed to get JSON from {url}: {resp.error if resp else 'No response'}")
        return None

    def set_timeout(self, timeout: float, connect_timeout: Optional[float] = None):
        self.read_timeout = timeout
        if connect_timeout is not None:
            self.connect_timeout = connect_timeout
        self._init_pool()

    def set_connect_timeout(self, timeout: float):
        self.connect_timeout = timeout
        self._init_pool()

    def set_read_timeout(self, timeout: float):
        self.read_timeout = timeout
        self._init_pool()

    def set_ssl_verification(self, verify: bool):
        self.verify_ssl = verify
        self._init_pool()

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
        self.use_retry = enabled
        self.retry_total = total
        self.retry_backoff = backoff
        if status_forcelist is not None:
            self.retry_status_forcelist = status_forcelist
        self._init_pool()

    def set_pool_config(self, num_pools: int = DEFAULT_NUM_POOLS,
                        maxsize: int = DEFAULT_POOL_MAXSIZE):
        self.num_pools = num_pools
        self.pool_maxsize = maxsize
        self._init_pool()

    def set_rate_limit(self, requests_per_second: float,
                       wait_timeout: Optional[float] = None):
        self.rate_limiter.set_rate(requests_per_second)
        with self._features_lock:
            self._features['rate_limit'] = requests_per_second > 0
        if wait_timeout is not None:
            self.rate_limiter.set_wait_timeout(wait_timeout)

    def set_user_agent_rotation(self, enabled: bool,
                                ua_list: Optional[List[str]] = None):
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

    def enable_logging(self, log_dir: str = 'logs', level: int = logging.INFO,
                       console: bool = True):
        logger.configure(enabled=True, log_dir=log_dir, level=level, console=console)

    def disable_logging(self):
        logger.configure(enabled=False)

    @property
    def logging_enabled(self) -> bool:
        return logger.enabled

    def enable_robots_respect(self, user_agent: Optional[str] = None,
                              timeout: Optional[float] = None):
        if user_agent:
            self._robots_user_agent = user_agent
        self.respect_robots = True
        with self._features_lock:
            self._features['robots'] = True
        robots_timeout = timeout if timeout is not None else 5.0
        self.robots_parser = RobotsParser(user_agent=self._robots_user_agent,
                                          timeout=robots_timeout)

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
            'retry_enabled': self.use_retry,
            'ua_rotation_enabled': self._get_feature('ua_rotation'),
            'referrer_set': self.referrer is not None,
            'connect_timeout': self.connect_timeout,
            'read_timeout': self.read_timeout,
            'auto_decompress': self.auto_decompress,
        }

    def clear_cache(self):
        if self.cache:
            self.cache.clear()

    def clear_history(self):
        with self._history_lock:
            self._history.clear()

    def export_history(self, format: str = 'json',
                       filepath: str = 'history_export') -> str:
        import csv
        with self._history_lock:
            history_list = list(self._history)
        if format == 'json':
            filepath = filepath + '.json'
            data = [{'method': r.method, 'url': r.url, 'status': r.status,
                     'duration': r.duration, 'timestamp': r.timestamp, 'error': r.error}
                    for r in history_list]
            with open(filepath, 'w', encoding='utf-8') as f:
                json_module.dump(data, f, indent=2, ensure_ascii=False)
        elif format == 'csv':
            filepath = filepath + '.csv'
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Method', 'URL', 'Status', 'Duration', 'Timestamp', 'Error'])
                for r in history_list:
                    writer.writerow([r.method, r.url, r.status, r.duration, r.timestamp, r.error])
        return filepath

    def get_last_response(self) -> Optional[HTTPResponse]:
        with self._last_response_lock:
            return self._last_response

    def get_history(self, limit: int = 100) -> List[RequestRecord]:
        with self._history_lock:
            history_list = list(self._history)
        return history_list[-limit:]

    def close(self):
        if self._pool:
            self._pool.clear()
        if self.cache:
            self.cache._cleanup_db()
        self.session_manager.clear()
