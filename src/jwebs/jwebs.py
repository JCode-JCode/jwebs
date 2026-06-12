# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import logging
import sys
import os
from typing import Optional, Dict, Any, List, Tuple, Union

from urllib.parse import urlparse
from .core.http import FastHTTP, HTTPResponse
from .core.datatypes import (
    TimeoutConfig, RequestRecord, SecurityReport, SEOScore, PerformanceMetrics,
    AIScrapingResult, CAPTCHAResult,
    AIConfig, CheckerConfig, CaptchaConfig, CrawlerConfig, RobotsConfig,
    LoggingConfig, RateLimitConfig, AsyncConfig, MonitorConfig, ProxyConfigGroup,
    ClientCertConfig, HTTPConfig
)
from .ai import GraphQLClient
from .core.constants import (
    DEFAULT_CACHE_TTL, DEFAULT_NUM_POOLS, DEFAULT_POOL_MAXSIZE, DEFAULT_MAX_WORKERS,
    DEFAULT_RATE_LIMIT, DEFAULT_RATE_LIMIT_TIMEOUT, DEFAULT_SESSION_IDLE_TIMEOUT,
    DEFAULT_HTTP_TIMEOUT, DEFAULT_CONNECT_TIMEOUT, DEFAULT_CRAWLER_DELAY, DEFAULT_MONITOR_INTERVAL
)
from .core.logging import logger
from .check import Checker
from .extract import Builder
from .crawl import Crawler, DistributedCrawler
from .diff import ContentDiffer
from .generate import SitemapGenerator, RSSGenerator
from .ai import AIScrapingEngine
from .captcha import CaptchaSolver
from .proxy import ProxyRotator
from .monitor import Monitor
from .smart import SmartScraper
from .async_ import AsyncClient

IS_ANDROID = hasattr(sys, 'getandroidapilevel') or 'ANDROID_STORAGE' in os.environ
IS_IOS = sys.platform == 'ios' or 'IPHONE' in os.environ


class JWebs:
    def __init__(self,
                 master_timeout: Optional[float] = None,
                 timeouts: Optional[Union[float, Tuple[float, float]]] = None,
                 timeout: Optional[float] = None,
                 connect_timeout: Optional[float] = None,
                 num_pools: int = DEFAULT_NUM_POOLS,
                 pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
                 max_workers: int = DEFAULT_MAX_WORKERS,
                 rate_limit: float = DEFAULT_RATE_LIMIT,
                 rate_limit_timeout: float = DEFAULT_RATE_LIMIT_TIMEOUT,
                 default_headers: Optional[Dict] = None,
                 use_random_ua: bool = False,
                 ua_list: Optional[List[str]] = None,
                 referrer: Optional[str] = None,
                 verify_ssl: bool = True,
                 use_retry: bool = False,
                 retry_total: int = 3,
                 retry_backoff: float = 0.1,
                 retry_status_forcelist: Optional[List[int]] = None,
                 use_cache: bool = False,
                 cache_ttl: float = DEFAULT_CACHE_TTL,
                 cache_max_item_size: Optional[int] = 5 * 1024 * 1024,
                 enable_logging: bool = False,
                 log_dir: str = 'logs',
                 log_level: int = logging.INFO,
                 log_console: bool = True,
                 respect_robots_txt: bool = False,
                 robots_user_agent: str = 'JWebs/2.0',
                 robots_timeout: Optional[float] = None,
                 session_idle_timeout: Optional[float] = None,
                 allow_expired_sessions: bool = False,
                 suppress_ssl_warnings: bool = True,
                 checker_ssl_timeout: Optional[float] = None,
                 checker_dns_timeout: Optional[float] = None,
                 checker_port_timeout: Optional[float] = None,
                 checker_ping_timeout: Optional[float] = None,
                 checker_status_timeout: Optional[float] = None,
                 checker_redirect_timeout: Optional[float] = None,
                 use_ai: bool = False,
                 ai_provider: str = 'deepseek',
                 ai_model: Optional[str] = None,
                 ai_api_key: Optional[str] = None,
                 ai_connect_timeout: Optional[float] = None,
                 ai_read_timeout: Optional[float] = None,
                 ai_total_timeout: Optional[float] = None,
                 ai_max_cache_entries: int = 100,
                 ai_cache_ttl_enabled: bool = False,
                 ai_cache_ttl_seconds: int = 3600,
                 captcha_connect_timeout: Optional[float] = None,
                 captcha_read_timeout: Optional[float] = None,
                 captcha_solve_timeout: Optional[float] = None,
                 use_proxy: bool = False,
                 monitor_check_timeout: Optional[float] = None,
                 monitor_interval: int = DEFAULT_MONITOR_INTERVAL,
                 crawler_request_timeout: Optional[float] = None,
                 crawler_delay: float = DEFAULT_CRAWLER_DELAY,
                 async_timeout: Optional[float] = None,
                 async_connect_timeout: Optional[float] = None,
                 redirects: Union[bool, int] = False,
                 client_cert: Optional[str] = None,
                 client_key: Optional[str] = None,
                 client_cert_password: Optional[str] = None,
                 ca_bundle: Optional[str] = None,
                 http: Optional[Union[Dict, HTTPConfig]] = None,
                 ai: Optional[Union[Dict, AIConfig]] = None,
                 checker: Optional[Union[Dict, CheckerConfig]] = None,
                 captcha: Optional[Union[Dict, CaptchaConfig]] = None,
                 crawler: Optional[Union[Dict, CrawlerConfig]] = None,
                 robots: Optional[Union[Dict, RobotsConfig]] = None,
                 logging: Optional[Union[Dict, LoggingConfig]] = None,
                 rate_limit_cfg: Optional[Union[Dict, RateLimitConfig]] = None,
                 async_cfg: Optional[Union[Dict, AsyncConfig]] = None,
                 monitor: Optional[Union[Dict, MonitorConfig]] = None,
                 proxy: Optional[Union[Dict, ProxyConfigGroup]] = None,
                 client_cert_cfg: Optional[Union[Dict, ClientCertConfig]] = None,
                 full_init: bool = True,
                 http_version: str = 'auto',
                 max_connections: Optional[int] = None):

        if http is not None:
            if isinstance(http, dict):
                http_cfg = HTTPConfig(**http)
            else:
                http_cfg = http
            if http_cfg.timeout is not None:
                timeout = http_cfg.timeout
            if http_cfg.connect_timeout is not None:
                connect_timeout = http_cfg.connect_timeout
            num_pools = http_cfg.num_pools
            pool_maxsize = http_cfg.pool_maxsize
            max_workers = http_cfg.max_workers
            if http_cfg.default_headers is not None:
                default_headers = http_cfg.default_headers
            use_random_ua = http_cfg.use_random_ua
            if http_cfg.ua_list is not None:
                ua_list = http_cfg.ua_list
            if http_cfg.referrer is not None:
                referrer = http_cfg.referrer
            verify_ssl = http_cfg.verify_ssl
            use_retry = http_cfg.use_retry
            retry_total = http_cfg.retry_total
            retry_backoff = http_cfg.retry_backoff
            if http_cfg.retry_status_forcelist is not None:
                retry_status_forcelist = http_cfg.retry_status_forcelist
            use_cache = http_cfg.use_cache
            cache_ttl = http_cfg.cache_ttl
            redirects = http_cfg.redirects
            suppress_ssl_warnings = http_cfg.suppress_ssl_warnings
            if http_cfg.session_idle_timeout is not None:
                session_idle_timeout = http_cfg.session_idle_timeout
            allow_expired_sessions = http_cfg.allow_expired_sessions

        if ai is not None:
            if isinstance(ai, dict):
                ai_cfg = AIConfig(**ai)
            else:
                ai_cfg = ai
            use_ai = ai_cfg.enabled
            ai_provider = ai_cfg.provider
            if ai_cfg.model is not None:
                ai_model = ai_cfg.model
            if ai_cfg.api_key is not None:
                ai_api_key = ai_cfg.api_key
            ai_connect_timeout = ai_cfg.connect_timeout
            ai_read_timeout = ai_cfg.read_timeout
            ai_total_timeout = ai_cfg.total_timeout
            ai_max_cache_entries = ai_cfg.max_cache_entries
            ai_cache_ttl_enabled = ai_cfg.cache_ttl_enabled
            ai_cache_ttl_seconds = ai_cfg.cache_ttl_seconds

        if checker is not None:
            if isinstance(checker, dict):
                chk_cfg = CheckerConfig(**checker)
            else:
                chk_cfg = checker
            if chk_cfg.ssl_timeout is not None:
                checker_ssl_timeout = chk_cfg.ssl_timeout
            if chk_cfg.dns_timeout is not None:
                checker_dns_timeout = chk_cfg.dns_timeout
            if chk_cfg.port_timeout is not None:
                checker_port_timeout = chk_cfg.port_timeout
            if chk_cfg.ping_timeout is not None:
                checker_ping_timeout = chk_cfg.ping_timeout
            if chk_cfg.status_timeout is not None:
                checker_status_timeout = chk_cfg.status_timeout
            if chk_cfg.redirect_timeout is not None:
                checker_redirect_timeout = chk_cfg.redirect_timeout

        if captcha is not None:
            if isinstance(captcha, dict):
                cap_cfg = CaptchaConfig(**captcha)
            else:
                cap_cfg = captcha
            captcha_connect_timeout = cap_cfg.connect_timeout
            captcha_read_timeout = cap_cfg.read_timeout
            captcha_solve_timeout = cap_cfg.solve_timeout

        if crawler is not None:
            if isinstance(crawler, dict):
                cr_cfg = CrawlerConfig(**crawler)
            else:
                cr_cfg = crawler
            if cr_cfg.request_timeout is not None:
                crawler_request_timeout = cr_cfg.request_timeout
            crawler_delay = cr_cfg.delay

        if robots is not None:
            if isinstance(robots, dict):
                rb_cfg = RobotsConfig(**robots)
            else:
                rb_cfg = robots
            respect_robots_txt = rb_cfg.respect
            robots_user_agent = rb_cfg.user_agent
            if rb_cfg.timeout is not None:
                robots_timeout = rb_cfg.timeout

        if logging is not None:
            if isinstance(logging, dict):
                log_cfg = LoggingConfig(**logging)
            else:
                log_cfg = logging
            enable_logging = log_cfg.enabled
            log_dir = log_cfg.log_dir
            log_level = log_cfg.level
            log_console = log_cfg.console

        if rate_limit_cfg is not None:
            if isinstance(rate_limit_cfg, dict):
                rl_cfg = RateLimitConfig(**rate_limit_cfg)
            else:
                rl_cfg = rate_limit_cfg
            rate_limit = rl_cfg.requests_per_second
            rate_limit_timeout = rl_cfg.wait_timeout

        if async_cfg is not None:
            if isinstance(async_cfg, dict):
                as_cfg = AsyncConfig(**async_cfg)
            else:
                as_cfg = async_cfg
            if as_cfg.timeout is not None:
                async_timeout = as_cfg.timeout
            if as_cfg.connect_timeout is not None:
                async_connect_timeout = as_cfg.connect_timeout

        if monitor is not None:
            if isinstance(monitor, dict):
                mon_cfg = MonitorConfig(**monitor)
            else:
                mon_cfg = monitor
            if mon_cfg.check_timeout is not None:
                monitor_check_timeout = mon_cfg.check_timeout
            monitor_interval = mon_cfg.check_interval

        if proxy is not None:
            if isinstance(proxy, dict):
                pr_cfg = ProxyConfigGroup(**proxy)
            else:
                pr_cfg = proxy
            use_proxy = pr_cfg.enabled

        if client_cert_cfg is not None:
            if isinstance(client_cert_cfg, dict):
                cert_cfg = ClientCertConfig(**client_cert_cfg)
            else:
                cert_cfg = client_cert_cfg
            if cert_cfg.cert is not None:
                client_cert = cert_cfg.cert
            if cert_cfg.key is not None:
                client_key = cert_cfg.key
            if cert_cfg.password is not None:
                client_cert_password = cert_cfg.password
            if cert_cfg.ca_bundle is not None:
                ca_bundle = cert_cfg.ca_bundle

        if master_timeout is not None:
            if not isinstance(master_timeout, (int, float)):
                raise TypeError(f"master_timeout must be a number, got {type(master_timeout).__name__}")
            if master_timeout <= 0:
                raise ValueError(f"master_timeout must be > 0, got {master_timeout}")
            effective_connect = master_timeout
            effective_read = master_timeout
            rate_limit_timeout = master_timeout
            robots_timeout = master_timeout
            session_idle_timeout = master_timeout if session_idle_timeout is None else session_idle_timeout
            checker_ssl_timeout = master_timeout
            checker_dns_timeout = master_timeout
            checker_port_timeout = master_timeout
            checker_ping_timeout = master_timeout
            checker_status_timeout = master_timeout
            checker_redirect_timeout = master_timeout
            ai_connect_timeout = master_timeout
            ai_read_timeout = master_timeout
            ai_total_timeout = master_timeout
            captcha_connect_timeout = master_timeout
            captcha_read_timeout = master_timeout
            captcha_solve_timeout = master_timeout
            monitor_check_timeout = master_timeout
            crawler_request_timeout = master_timeout
            async_timeout = master_timeout
            async_connect_timeout = master_timeout
            logger.info('JWebs', f"Master timeout set to {master_timeout}s")
        else:
            if timeouts is not None:
                if isinstance(timeouts, (int, float)):
                    effective_connect = timeouts
                    effective_read = timeouts
                elif isinstance(timeouts, tuple) and len(timeouts) == 2:
                    effective_connect, effective_read = timeouts
                else:
                    raise TypeError("timeouts must be a number or a tuple of two numbers")
            else:
                effective_connect = connect_timeout if connect_timeout is not None else DEFAULT_CONNECT_TIMEOUT
                effective_read = timeout if timeout is not None else DEFAULT_HTTP_TIMEOUT
            if robots_timeout is None:
                robots_timeout = None
            if session_idle_timeout is None:
                session_idle_timeout = DEFAULT_SESSION_IDLE_TIMEOUT

        if IS_ANDROID or IS_IOS:
            num_pools = min(num_pools, 10)
            max_workers = min(max_workers, 5)
            pool_maxsize = min(pool_maxsize, 20)
            if effective_read is not None:
                effective_read = max(effective_read, 15.0)
            if effective_connect is not None:
                effective_connect = max(effective_connect, 10.0)

        if monitor_interval is None:
            monitor_interval = DEFAULT_MONITOR_INTERVAL

        self._proxy_rotator = ProxyRotator() if use_proxy else None

        if max_connections is None:
            max_connections = max_workers * 2

        if http_version == '2':
            from .core.http2 import HTTPXClient
            self.http = HTTPXClient(
                http_version='2',
                timeout=effective_read,
                connect_timeout=effective_connect,
                verify_ssl=verify_ssl,
                default_headers=default_headers,
                use_cache=use_cache,
                cache_ttl=cache_ttl,
                cache_max_item_size=cache_max_item_size,
                rate_limit=rate_limit,
                rate_limit_timeout=rate_limit_timeout,
                respect_robots_txt=respect_robots_txt,
                robots_user_agent=robots_user_agent,
                robots_timeout=robots_timeout if robots_timeout is not None else 5.0,
                use_proxy=use_proxy,
                proxy_rotator=self._proxy_rotator,
                session_idle_timeout=session_idle_timeout,
                allow_expired_sessions=allow_expired_sessions,
                max_connections=max_connections
            )
            self.http.use_random_ua = use_random_ua
            self.http._ua_list = ua_list or []
            self.http.referrer = referrer
            self.http.use_retry = use_retry
            self.http.retry_total = retry_total
            self.http.retry_backoff = retry_backoff
            self.http.retry_status_forcelist = retry_status_forcelist
            self.http.redirects = redirects
        else:
            self.http = FastHTTP(
                num_pools=num_pools,
                default_headers=default_headers,
                timeout=effective_read,
                connect_timeout=effective_connect,
                use_cache=use_cache,
                cache_ttl=cache_ttl,
                cache_max_item_size=cache_max_item_size,
                rate_limit=rate_limit,
                rate_limit_timeout=rate_limit_timeout,
                max_workers=max_workers,
                use_random_ua=use_random_ua,
                ua_list=ua_list,
                referrer=referrer,
                enable_logging=enable_logging,
                log_dir=log_dir,
                log_level=log_level,
                log_console=log_console,
                respect_robots_txt=respect_robots_txt,
                robots_user_agent=robots_user_agent,
                robots_timeout=robots_timeout if robots_timeout is not None else 5.0,
                verify_ssl=verify_ssl,
                use_retry=use_retry,
                retry_total=retry_total,
                retry_backoff=retry_backoff,
                retry_status_forcelist=retry_status_forcelist,
                pool_maxsize=pool_maxsize,
                session_idle_timeout=session_idle_timeout,
                allow_expired_sessions=allow_expired_sessions,
                suppress_ssl_warnings=suppress_ssl_warnings,
                redirects=redirects,
                use_proxy=use_proxy,
                proxy_rotator=self._proxy_rotator,
                client_cert=client_cert,
                client_key=client_key,
                client_cert_password=client_cert_password,
                ca_bundle=ca_bundle
            )

        self._init_kwargs = {
            'checker_ssl_timeout': checker_ssl_timeout,
            'checker_dns_timeout': checker_dns_timeout,
            'checker_port_timeout': checker_port_timeout,
            'checker_ping_timeout': checker_ping_timeout,
            'checker_status_timeout': checker_status_timeout,
            'checker_redirect_timeout': checker_redirect_timeout,
            'use_ai': use_ai,
            'ai_provider': ai_provider,
            'ai_model': ai_model,
            'ai_api_key': ai_api_key,
            'ai_connect_timeout': ai_connect_timeout,
            'ai_read_timeout': ai_read_timeout,
            'ai_total_timeout': ai_total_timeout,
            'ai_max_cache_entries': ai_max_cache_entries,
            'ai_cache_ttl_enabled': ai_cache_ttl_enabled,
            'ai_cache_ttl_seconds': ai_cache_ttl_seconds,
            'captcha_connect_timeout': captcha_connect_timeout,
            'captcha_read_timeout': captcha_read_timeout,
            'captcha_solve_timeout': captcha_solve_timeout,
            'use_proxy': use_proxy,
            'monitor_check_timeout': monitor_check_timeout,
            'monitor_interval': monitor_interval,
            'crawler_request_timeout': crawler_request_timeout,
            'crawler_delay': crawler_delay,
            'async_timeout': async_timeout,
            'async_connect_timeout': async_connect_timeout,
            'respect_robots_txt': respect_robots_txt,
            'max_workers': max_workers,
            'robots_timeout': robots_timeout,
            'http_version': http_version,
            'max_connections': max_connections,
            'cache_max_item_size': cache_max_item_size,
        }
        self._full_init = full_init

        if full_init:
            self._build_all_components()
        else:
            self._checker = None
            self._builder = None
            self._crawler = None
            self._differ = None
            self._sitemap_gen = None
            self._rss_gen = None
            self._ai_engine = None
            self._captcha_solver = None
            self._monitor = None
            self._distributed_crawler = None
            self._smart_scraper = None
            self._async_client = None

        self._version = __import__('jwebs').__version__
        self._platform = 'android' if IS_ANDROID else ('ios' if IS_IOS else sys.platform)
        self._master_timeout = master_timeout
        self._crawler_delay = crawler_delay
        self._monitor_interval = monitor_interval

        http_total = None
        if effective_read is not None and effective_connect is not None:
            http_total = effective_read + effective_connect

        self._timeout_config = TimeoutConfig(
            http_connect=effective_connect,
            http_read=effective_read,
            http_total=http_total,
            checker_ssl=checker_ssl_timeout,
            checker_dns=checker_dns_timeout,
            checker_port=checker_port_timeout,
            checker_ping=checker_ping_timeout,
            checker_status=checker_status_timeout,
            checker_redirect=checker_redirect_timeout,
            robots_fetch=robots_timeout,
            ai_connect=ai_connect_timeout,
            ai_read=ai_read_timeout,
            ai_total=ai_total_timeout,
            captcha_connect=captcha_connect_timeout,
            captcha_read=captcha_read_timeout,
            captcha_solve=captcha_solve_timeout,
            rate_limit_timeout=rate_limit_timeout,
            monitor_check=monitor_check_timeout,
            crawler_request=crawler_request_timeout,
            async_timeout=async_timeout,
            session_idle=session_idle_timeout
        )

    def _build_all_components(self):
        kwargs = self._init_kwargs
        self._checker = Checker(
            self.http,
            ssl_timeout=kwargs['checker_ssl_timeout'],
            dns_timeout=kwargs['checker_dns_timeout'],
            port_timeout=kwargs['checker_port_timeout'],
            ping_timeout=kwargs['checker_ping_timeout'],
            status_timeout=kwargs['checker_status_timeout'],
            redirect_timeout=kwargs['checker_redirect_timeout']
        )
        self._builder = Builder(self.http)
        self._crawler = Crawler(self.http, request_timeout=kwargs['crawler_request_timeout'],
                                delay=kwargs['crawler_delay'])
        self._differ = ContentDiffer()
        self._sitemap_gen = SitemapGenerator()
        self._rss_gen = RSSGenerator()

        if kwargs['use_ai']:
            self._ai_engine = AIScrapingEngine(
                provider=kwargs['ai_provider'],
                model=kwargs['ai_model'],
                api_key=kwargs['ai_api_key'],
                connect_timeout=kwargs['ai_connect_timeout'],
                read_timeout=kwargs['ai_read_timeout'],
                total_timeout=kwargs['ai_total_timeout'],
                max_cache_entries=kwargs['ai_max_cache_entries'],
                cache_ttl_enabled=kwargs['ai_cache_ttl_enabled'],
                cache_ttl_seconds=kwargs['ai_cache_ttl_seconds']
            )
        else:
            self._ai_engine = None

        self._captcha_solver = CaptchaSolver(
            connect_timeout=kwargs['captcha_connect_timeout'],
            read_timeout=kwargs['captcha_read_timeout'],
            solve_timeout=kwargs['captcha_solve_timeout']
        )

        if kwargs['use_proxy'] and self._proxy_rotator is None:
            self._proxy_rotator = ProxyRotator()

        self._monitor = Monitor(check_interval=kwargs['monitor_interval'],
                                check_timeout=kwargs['monitor_check_timeout'])
        self._distributed_crawler = DistributedCrawler(
            http=self.http,
            request_timeout=kwargs['crawler_request_timeout']
        )
        self._smart_scraper = SmartScraper(
            use_ai=kwargs['use_ai'], use_proxy=kwargs['use_proxy'],
            respect_robots=kwargs['respect_robots_txt'], http=self.http
        )
        self._async_client = AsyncClient(
            max_connections=kwargs['max_workers'] * 2,
            timeout=kwargs['async_timeout'],
            connect_timeout=kwargs['async_connect_timeout']
        )

    @property
    def checker(self):
        if self._checker is None:
            kwargs = self._init_kwargs
            self._checker = Checker(
                self.http,
                ssl_timeout=kwargs['checker_ssl_timeout'],
                dns_timeout=kwargs['checker_dns_timeout'],
                port_timeout=kwargs['checker_port_timeout'],
                ping_timeout=kwargs['checker_ping_timeout'],
                status_timeout=kwargs['checker_status_timeout'],
                redirect_timeout=kwargs['checker_redirect_timeout']
            )
        return self._checker

    @property
    def builder(self):
        if self._builder is None:
            self._builder = Builder(self.http)
        return self._builder

    @property
    def crawler(self):
        if self._crawler is None:
            kwargs = self._init_kwargs
            self._crawler = Crawler(self.http, request_timeout=kwargs['crawler_request_timeout'],
                                    delay=kwargs['crawler_delay'])
        return self._crawler

    @property
    def differ(self):
        if self._differ is None:
            self._differ = ContentDiffer()
        return self._differ

    @property
    def sitemap_gen(self):
        if self._sitemap_gen is None:
            self._sitemap_gen = SitemapGenerator()
        return self._sitemap_gen

    @property
    def rss_gen(self):
        if self._rss_gen is None:
            self._rss_gen = RSSGenerator()
        return self._rss_gen

    @property
    def ai_engine(self):
        if self._ai_engine is None and self._init_kwargs['use_ai']:
            kwargs = self._init_kwargs
            self._ai_engine = AIScrapingEngine(
                provider=kwargs['ai_provider'],
                model=kwargs['ai_model'],
                api_key=kwargs['ai_api_key'],
                connect_timeout=kwargs['ai_connect_timeout'],
                read_timeout=kwargs['ai_read_timeout'],
                total_timeout=kwargs['ai_total_timeout'],
                max_cache_entries=kwargs['ai_max_cache_entries'],
                cache_ttl_enabled=kwargs['ai_cache_ttl_enabled'],
                cache_ttl_seconds=kwargs['ai_cache_ttl_seconds']
            )
        return self._ai_engine

    @property
    def captcha_solver(self):
        if self._captcha_solver is None:
            kwargs = self._init_kwargs
            self._captcha_solver = CaptchaSolver(
                connect_timeout=kwargs['captcha_connect_timeout'],
                read_timeout=kwargs['captcha_read_timeout'],
                solve_timeout=kwargs['captcha_solve_timeout']
            )
        return self._captcha_solver

    @property
    def proxy_rotator(self):
        if self._proxy_rotator is None and self._init_kwargs['use_proxy']:
            self._proxy_rotator = ProxyRotator()
        return self._proxy_rotator

    @property
    def monitor(self):
        if self._monitor is None:
            kwargs = self._init_kwargs
            self._monitor = Monitor(check_interval=kwargs['monitor_interval'],
                                    check_timeout=kwargs['monitor_check_timeout'])
        return self._monitor

    @property
    def distributed_crawler(self):
        if self._distributed_crawler is None:
            self._distributed_crawler = DistributedCrawler(http=self.http)
        return self._distributed_crawler

    @property
    def smart_scraper(self):
        if self._smart_scraper is None:
            kwargs = self._init_kwargs
            self._smart_scraper = SmartScraper(
                use_ai=kwargs['use_ai'], use_proxy=kwargs['use_proxy'],
                respect_robots=kwargs['respect_robots_txt'], http=self.http
            )
        return self._smart_scraper

    @property
    def async_client(self):
        if self._async_client is None:
            kwargs = self._init_kwargs
            self._async_client = AsyncClient(
                max_connections=kwargs['max_workers'] * 2,
                timeout=kwargs['async_timeout'],
                connect_timeout=kwargs['async_connect_timeout']
            )
        return self._async_client

    @property
    def robots_enabled(self) -> bool:
        return self.http.robots_enabled if hasattr(self.http, 'robots_enabled') else False

    def GET(self, url: str, **kwargs) -> HTTPResponse:
        return self.http.GET(url, **kwargs)

    def POST(self, url: str, **kwargs) -> HTTPResponse:
        return self.http.POST(url, **kwargs)

    def PUT(self, url: str, **kwargs) -> HTTPResponse:
        return self.http.PUT(url, **kwargs)

    def PATCH(self, url: str, **kwargs) -> HTTPResponse:
        return self.http.PATCH(url, **kwargs)

    def DELETE(self, url: str, **kwargs) -> HTTPResponse:
        return self.http.DELETE(url, **kwargs)

    def HEAD(self, url: str, **kwargs) -> HTTPResponse:
        return self.http.HEAD(url, **kwargs)

    def OPTIONS(self, url: str, **kwargs) -> HTTPResponse:
        return self.http.OPTIONS(url, **kwargs)

    def TEXT(self, url: str, **kwargs) -> Optional[str]:
        return self.http.TEXT(url, **kwargs)

    def JSON(self, url: str, **kwargs) -> Optional[Any]:
        return self.http.JSON(url, **kwargs)

    def BATCH(self, urls: List[str], method: str = 'GET', max_workers: Optional[int] = None,
              raise_on_error: bool = False, **kwargs) -> Dict[str, Any]:
        return self.http.BATCH(urls, method, max_workers, raise_on_error, **kwargs)

    def SET_FEATURES(self, **kwargs):
        if hasattr(self.http, 'set_features'):
            self.http.set_features(**kwargs)

    def ENABLE_FEATURE(self, feature: str):
        if hasattr(self.http, 'enable_feature'):
            self.http.enable_feature(feature)

    def DISABLE_FEATURE(self, feature: str):
        if hasattr(self.http, 'disable_feature'):
            self.http.disable_feature(feature)

    def DISABLE_ALL_FEATURES(self):
        if hasattr(self.http, '_features'):
            for f in self.http._features:
                self.http._features[f] = False

    def ENABLE_ALL_FEATURES(self):
        if hasattr(self.http, '_features'):
            for f in self.http._features:
                self.http._features[f] = True

    def ENABLE_QUICK_MODE(self):
        if hasattr(self.http, 'enable_quick_mode'):
            self.http.enable_quick_mode()

    def DISABLE_QUICK_MODE(self):
        if hasattr(self.http, 'disable_quick_mode'):
            self.http.disable_quick_mode()

    @property
    def FEATURES(self) -> Dict[str, bool]:
        if hasattr(self.http, 'feature_flags'):
            return self.http.feature_flags
        return {}

    def GET_TIMEOUT_CONFIG(self) -> TimeoutConfig:
        return self._timeout_config

    def SET_HTTP_TIMEOUTS(self, connect: Optional[float] = None, read: Optional[float] = None):
        if connect is not None or read is not None:
            if hasattr(self.http, 'set_timeout'):
                self.http.set_timeout(
                    timeout=read if read is not None else self.http.read_timeout,
                    connect_timeout=connect if connect is not None else self.http.connect_timeout
                )
            if connect:
                self._timeout_config.http_connect = connect
            if read:
                self._timeout_config.http_read = read

    def SET_CHECKER_TIMEOUTS(self, ssl: Optional[float] = None, dns: Optional[float] = None,
                             port: Optional[float] = None, ping: Optional[float] = None,
                             status: Optional[float] = None, redirect: Optional[float] = None):
        self.checker.set_timeouts(ssl=ssl, dns=dns, port=port, ping=ping, status=status, redirect=redirect)
        if ssl: self._timeout_config.checker_ssl = ssl
        if dns: self._timeout_config.checker_dns = dns
        if port: self._timeout_config.checker_port = port
        if ping: self._timeout_config.checker_ping = ping
        if status: self._timeout_config.checker_status = status
        if redirect: self._timeout_config.checker_redirect = redirect

    def SET_AI_TIMEOUTS(self, connect: Optional[float] = None, read: Optional[float] = None,
                        total: Optional[float] = None):
        if self.ai_engine:
            self.ai_engine.set_timeouts(connect=connect, read=read, total=total)
            if connect: self._timeout_config.ai_connect = connect
            if read: self._timeout_config.ai_read = read
            if total: self._timeout_config.ai_total = total

    def SET_CAPTCHA_TIMEOUTS(self, connect: Optional[float] = None, read: Optional[float] = None,
                             solve: Optional[float] = None):
        self.captcha_solver.set_timeouts(connect=connect, read=read, solve=solve)
        if connect: self._timeout_config.captcha_connect = connect
        if read: self._timeout_config.captcha_read = read
        if solve: self._timeout_config.captcha_solve = solve

    def SET_ROBOTS_TIMEOUT(self, timeout: float):
        if hasattr(self.http, 'set_robots_timeout'):
            self.http.set_robots_timeout(timeout)
        self._timeout_config.robots_fetch = timeout

    def SET_RATE_LIMIT(self, requests_per_second: float, wait_timeout: Optional[float] = None):
        if hasattr(self.http, 'set_rate_limit'):
            self.http.set_rate_limit(requests_per_second, wait_timeout)
        if wait_timeout: self._timeout_config.rate_limit_timeout = wait_timeout

    def SET_SESSION_IDLE_TIMEOUT(self, timeout: float):
        if hasattr(self.http, 'set_session_idle_timeout'):
            self.http.set_session_idle_timeout(timeout)
        self._timeout_config.session_idle = timeout

    def SET_MONITOR_TIMEOUT(self, timeout: float):
        self.monitor.check_timeout = timeout
        self._timeout_config.monitor_check = timeout

    def SET_MONITOR_INTERVAL(self, interval: int):
        self.monitor.check_interval = interval
        if self.monitor._running:
            self.monitor.STOP()
            self.monitor.START()

    def SET_TIMEOUT(self, timeout: float):
        self.SET_HTTP_TIMEOUTS(read=timeout)
        self.SET_CHECKER_TIMEOUTS(ssl=timeout, dns=timeout, ping=timeout, status=timeout)

    def SET_SSL_VERIFICATION(self, verify: bool):
        if hasattr(self.http, 'set_ssl_verification'):
            self.http.set_ssl_verification(verify)

    def SET_CACHE(self, enabled: bool, ttl: float = DEFAULT_CACHE_TTL):
        if hasattr(self.http, 'set_cache'):
            self.http.set_cache(enabled, ttl)

    def SET_RETRY(self, enabled: bool, total: int = 3, backoff: float = 0.1):
        if hasattr(self.http, 'set_retry'):
            self.http.set_retry(enabled, total, backoff)

    def SET_POOL_CONFIG(self, num_pools: int = DEFAULT_NUM_POOLS, maxsize: int = DEFAULT_POOL_MAXSIZE):
        if hasattr(self.http, 'set_pool_config'):
            self.http.set_pool_config(num_pools, maxsize)

    def SET_USER_AGENT_ROTATION(self, enabled: bool, ua_list: Optional[List[str]] = None):
        if hasattr(self.http, 'set_user_agent_rotation'):
            self.http.set_user_agent_rotation(enabled, ua_list)

    def SET_REFERRER(self, referrer: Optional[str]):
        if hasattr(self.http, 'set_referrer'):
            self.http.set_referrer(referrer)

    def ENABLE_LOGGING(self, log_dir: str = 'logs', level: int = logging.INFO, console: bool = True):
        if hasattr(self.http, 'enable_logging'):
            self.http.enable_logging(log_dir, level, console)

    def DISABLE_LOGGING(self):
        if hasattr(self.http, 'disable_logging'):
            self.http.disable_logging()

    def ENABLE_ROBOTS_RESPECT(self, user_agent: Optional[str] = None, timeout: Optional[float] = None):
        if hasattr(self.http, 'enable_robots_respect'):
            self.http.enable_robots_respect(user_agent, timeout)

    def DISABLE_ROBOTS_RESPECT(self):
        if hasattr(self.http, 'disable_robots_respect'):
            self.http.disable_robots_respect()

    def HAS_SSL(self, url: str) -> bool:
        return self.checker.has_ssl(url)

    def GET_SSL_INFO(self, url: str) -> Optional[Dict]:
        return self.checker.get_ssl_info(url)

    def IS_HTTPS(self, url: str) -> bool:
        return self.checker.is_https(url)

    def CHECK_SECURITY_HEADERS(self, url: str) -> Dict[str, bool]:
        return self.checker.check_security_headers(url)

    def GET_SECURITY_SCORE(self, url: str) -> Tuple[int, Dict]:
        return self.checker.get_security_score(url)

    def IS_UP(self, url: str, timeout: Optional[float] = None) -> bool:
        return self.checker.is_up(url, timeout)

    def IS_DOWN(self, url: str) -> bool:
        return self.checker.is_down(url)

    def PING(self, url: str, count: int = 3, timeout: Optional[float] = None) -> Dict:
        return self.checker.ping(url, count, timeout)

    def STATUS_CODE(self, url: str, timeout: Optional[float] = None) -> Optional[int]:
        return self.checker.status_code(url, timeout)

    def IS_2XX(self, url: str) -> bool:
        return self.checker.is_2xx(url)

    def IS_3XX(self, url: str) -> bool:
        return self.checker.is_3xx(url)

    def IS_4XX(self, url: str) -> bool:
        return self.checker.is_4xx(url)

    def IS_5XX(self, url: str) -> bool:
        return self.checker.is_5xx(url)

    def GET_HEADERS(self, url: str, timeout: Optional[float] = None) -> Dict:
        return self.checker.get_headers(url, timeout)

    def DETECT_TECH(self, url: str) -> Dict[str, List[str]]:
        return self.checker.detect_tech(url)

    def IS_VALID_URL(self, url: str) -> bool:
        return self.checker.is_valid_url(url)

    def PARSE_URL(self, url: str) -> Dict:
        return self.checker.parse_url(url)

    def SECURITY_AUDIT(self, url: str) -> SecurityReport:
        return self.checker.security_audit(url)

    def SEO_AUDIT(self, url: str) -> SEOScore:
        return self.checker.seo_audit(url)

    def PERFORMANCE_TEST(self, url: str, runs: int = 3) -> PerformanceMetrics:
        return self.checker.performance_test(url, runs)

    def ANALYZE_REDIRECTS(self, url: str, timeout: Optional[float] = None) -> Dict:
        return self.checker.analyze_redirects(url, timeout)

    def GET_DNS_INFO(self, url: str) -> Optional[Dict]:
        return self.checker.get_dns_info(url)

    def CHECK_PORT(self, host: str, port: int, timeout: Optional[float] = None) -> bool:
        return self.checker.check_port(host, port, timeout)

    def GET_TEXT(self, url: str, **kwargs) -> List[str]:
        return self.builder.GET_TEXT(url, **kwargs)

    def GET_ALL_TEXT(self, url: str, **kwargs) -> str:
        return self.builder.GET_ALL_TEXT(url, **kwargs)

    def GET_TITLE(self, url: str, **kwargs) -> Optional[str]:
        return self.builder.GET_TITLE(url, **kwargs)

    def GET_LINKS(self, url: str, **kwargs) -> List[str]:
        return self.builder.GET_LINKS(url, **kwargs)

    def GET_IMAGES(self, url: str, **kwargs) -> List[Dict]:
        return self.builder.GET_IMAGES(url, **kwargs)

    def GET_METAS(self, url: str, **kwargs) -> List[Dict]:
        return self.builder.GET_METAS(url, **kwargs)

    def GET_META_DESC(self, url: str, **kwargs) -> Optional[str]:
        return self.builder.GET_META_DESC(url, **kwargs)

    def GET_JSONLD(self, url: str, **kwargs) -> List[Dict]:
        return self.builder.GET_JSONLD(url, **kwargs)

    def EXTRACT_EMAILS(self, url: str, **kwargs) -> List[str]:
        return self.builder.EXTRACT_EMAILS(url, **kwargs)

    def EXTRACT_PHONES(self, url: str, **kwargs) -> List[str]:
        return self.builder.EXTRACT_PHONES(url, **kwargs)

    def EXTRACT_PRICES(self, url: str, **kwargs) -> List[Dict]:
        return self.builder.EXTRACT_PRICES(url, **kwargs)

    def SENTIMENT(self, text: str) -> Dict:
        return self.builder.SENTIMENT(text)

    def TRANSLATE(self, text: str, target_lang: str = 'en') -> str:
        return self.builder.TRANSLATE(text, target_lang)

    def GET_HEADINGS(self, url: str, **kwargs) -> Dict[str, List[str]]:
        return self.builder.GET_HEADINGS(url, **kwargs)

    def GET_SOCIAL(self, url: str, **kwargs) -> Dict[str, List[str]]:
        return self.builder.GET_SOCIAL(url, **kwargs)

    def TO_JSON(self, data: Any, filepath: str, pretty: bool = True) -> str:
        return self.builder.TO_JSON(data, filepath, pretty)

    def TO_CSV(self, data: List[Dict], filepath: str) -> str:
        return self.builder.TO_CSV(data, filepath)

    def CRAWL(self, start_url: str, max_depth: int = 3, max_pages: int = 100,
              same_domain: bool = True, delay: Optional[float] = None) -> Dict[str, Dict]:
        return self.crawler.CRAWL(start_url, max_depth, max_pages, same_domain, delay=delay)

    def TAKE_SNAPSHOT(self, name: str, content: str) -> str:
        return self.differ.TAKE_SNAPSHOT(name, content)

    def COMPARE_SNAPSHOTS(self, id1: str, id2: str) -> Dict:
        return self.differ.COMPARE(id1, id2)

    def SIMILARITY(self, text1: str, text2: str) -> float:
        return self.differ.SIMILARITY(text1, text2)

    def GENERATE_SITEMAP(self, urls: List[str], filepath: str = 'sitemap.xml',
                         changefreq: str = 'weekly', priority: float = 0.8) -> str:
        return self.sitemap_gen.GENERATE(urls, filepath, changefreq, priority)

    def GENERATE_RSS(self, items: List[Dict], title: str, link: str,
                     description: str, filepath: str = 'feed.xml') -> str:
        return self.rss_gen.GENERATE(items, title, link, description, filepath)

    def GRAPHQL(self, endpoint: str, **kwargs) -> GraphQLClient:
        return GraphQLClient(endpoint, http=self.http, **kwargs)

    def AI_EXTRACT(self, html: str, instruction: str) -> AIScrapingResult:
        if self.ai_engine:
            return self.ai_engine.EXTRACT(html, instruction)
        return AIScrapingResult(elements=[{'error': 'AI engine not enabled. Set use_ai=True'}])

    def AI_SUMMARIZE(self, text: str, max_length: int = 150) -> str:
        if self.ai_engine:
            return self.ai_engine.SUMMARIZE(text, max_length)
        return text

    def AI_SCRAPE_PAGE(self, url: str, instruction: str) -> AIScrapingResult:
        if self.ai_engine:
            return self.ai_engine.SCRAPE_PAGE(url, instruction, self.http)
        return AIScrapingResult(elements=[{'error': 'AI engine not enabled. Set use_ai=True'}])

    def DETECT_CAPTCHA(self, html: str) -> Optional[str]:
        return self.captcha_solver.DETECT(html)

    def SOLVE_CAPTCHA(self, site_key: str, page_url: str) -> CAPTCHAResult:
        return self.captcha_solver.SOLVE(site_key, page_url)

    def ADD_PROXY(self, host: str, port: int, **kwargs):
        if self.proxy_rotator:
            self.proxy_rotator.ADD_PROXY(host, port, **kwargs)

    def GET_PROXY(self) -> Optional[Dict]:
        if self.proxy_rotator:
            return self.proxy_rotator.GET_PROXY()
        return None

    def MONITOR_URL(self, url: str, expected_status: int = 200) -> str:
        return self.monitor.ADD_URL(url, expected_status)

    def UNMONITOR_URL(self, url_id: str):
        self.monitor.REMOVE_URL(url_id)

    def START_MONITORING(self):
        self.monitor.START()

    def STOP_MONITORING(self):
        self.monitor.STOP()

    def GET_MONITOR_STATUS(self):
        return self.monitor

    def DISTRIBUTED_CRAWL(self, start_url: str, max_pages: int = 100,
                          max_depth: int = 3, strict_page_limit: bool = False,
                          same_domain: bool = True, delay: float = 0.2,
                          force_clear: bool = False) -> Dict[str, Dict]:
        crawler = self.distributed_crawler
        if force_clear:
            crawler.clear()
        crawler.add_seed(start_url, depth=0)
        crawler.crawl_worker(max_pages=max_pages, max_depth=max_depth,
                             same_domain=same_domain, delay=delay,
                             strict_page_limit=strict_page_limit)
        return crawler.get_all_results()

    def create_distributed_crawler(self, redis_url: str = "redis://localhost:6379/0",
                                   queue_name: str = "jwebs:crawl:tasks",
                                   visited_set: str = "jwebs:crawl:visited",
                                   result_hash: str = "jwebs:crawl:results",
                                   request_timeout: Optional[float] = None,
                                   respect_robots: Optional[bool] = None,
                                   **kwargs) -> DistributedCrawler:
        from .crawl import DistributedCrawler
        timeout = request_timeout if request_timeout is not None else self._init_kwargs.get('crawler_request_timeout', 10.0)
        robots = respect_robots if respect_robots is not None else self._init_kwargs.get('respect_robots_txt', False)
        return DistributedCrawler(
            redis_url=redis_url,
            queue_name=queue_name,
            visited_set=visited_set,
            result_hash=result_hash,
            http=self.http,
            request_timeout=timeout,
            respect_robots=robots,
            **kwargs
        )

    def SCRAPE(self, url: str, instruction: Optional[str] = None) -> Dict:
        return self.smart_scraper.SCRAPE(url, instruction)

    def SCRAPE_MULTI(self, urls: List[str], instruction: Optional[str] = None,
                     max_concurrent: int = 5) -> Dict[str, Dict]:
        return self.smart_scraper.SCRAPE_MULTI(urls, instruction, max_concurrent)

    def GET_STATS(self) -> Dict:
        return self.http.get_stats() if hasattr(self.http, 'get_stats') else {}

    def GET_HISTORY(self, limit: int = 100) -> List[RequestRecord]:
        return self.http.get_history(limit) if hasattr(self.http, 'get_history') else []

    def GET_LAST_RESPONSE(self) -> Optional[HTTPResponse]:
        return self.http.get_last_response() if hasattr(self.http, 'get_last_response') else None

    def CLEAR_CACHE(self):
        if hasattr(self.http, 'clear_cache'):
            self.http.clear_cache()

    def CLEAR_HISTORY(self):
        if hasattr(self.http, 'clear_history'):
            self.http.clear_history()

    def EXPORT_HISTORY(self, format: str = 'json', filepath: str = 'history_export') -> str:
        if hasattr(self.http, 'export_history'):
            return self.http.export_history(format, filepath)
        return ""

    def CLOSE(self):
        if hasattr(self.http, 'close'):
            self.http.close()
        if self._distributed_crawler:
            self._distributed_crawler.CLOSE()
        if self._async_client:
            self._async_client.CLOSE()
        if self._ai_engine:
            self._ai_engine.CLEAR_CACHE()

    def IS_PLATFORM_SUPPORTED(self) -> Dict:
        return {
            'platform': self._platform,
            'async_available': True,
            'ai_available': self.ai_engine is not None,
            'version': self._version,
            'timeouts': self._timeout_config
        }