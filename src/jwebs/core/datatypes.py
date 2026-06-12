# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime

@dataclass
class TimeoutConfig:
    http_connect: float = 10.0
    http_read: float = 30.0
    http_total: Optional[float] = None
    checker_ssl: float = 5.0
    checker_dns: float = 5.0
    checker_port: float = 2.0
    checker_ping: float = 3.0
    checker_status: float = 5.0
    checker_redirect: float = 5.0
    robots_fetch: float = 5.0
    ai_connect: float = 10.0
    ai_read: float = 60.0
    ai_total: float = 120.0
    captcha_connect: float = 10.0
    captcha_read: float = 30.0
    captcha_solve: float = 180.0
    rate_limit_timeout: float = 30.0
    monitor_check: float = 10.0
    crawler_request: float = 10.0
    async_timeout: float = 30.0
    session_idle: float = 3600.0

    def __post_init__(self):
        if self.http_total is None and self.http_read is not None and self.http_connect is not None:
            self.http_total = self.http_read + self.http_connect

@dataclass
class RequestRecord:
    method: str
    url: str
    status: Optional[int] = None
    timestamp: float = field(default_factory=float)
    duration: float = 0.0
    headers_sent: Dict = field(default_factory=dict)
    headers_received: Dict = field(default_factory=dict)
    content_length: int = 0
    content_type: str = ''
    error: Optional[str] = None
    redirect_chain: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.timestamp == 0.0:
            import time
            self.timestamp = time.time()

@dataclass
class CacheEntry:
    data: Any
    timestamp: float
    ttl: float
    etag: Optional[str] = None
    last_modified: Optional[str] = None

@dataclass
class ProxyConfig:
    host: str
    port: int
    protocol: str = 'http'
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None
    last_used: float = 0
    success_count: int = 0
    fail_count: int = 0

@dataclass
class SecurityReport:
    url: str
    ssl_valid: bool = False
    ssl_expiry: Optional[datetime] = None
    ssl_issuer: str = ''
    security_headers: Dict[str, bool] = field(default_factory=dict)
    vulnerabilities: List[Dict] = field(default_factory=list)
    score: int = 0
    grade: str = 'F'
    scan_time: float = field(default_factory=float)

    def __post_init__(self):
        if self.scan_time == 0.0:
            import time
            self.scan_time = time.time()

@dataclass
class SEOScore:
    overall: int = 0
    on_page: int = 0
    technical: int = 0
    content: int = 0
    mobile: int = 0
    speed: int = 0
    recommendations: List[str] = field(default_factory=list)
    analyzed_at: float = field(default_factory=float)

    def __post_init__(self):
        if self.analyzed_at == 0.0:
            import time
            self.analyzed_at = time.time()

@dataclass
class PerformanceMetrics:
    ttfb: float = 0.0
    dom_interactive: float = 0.0
    dom_complete: float = 0.0
    load_time: float = 0.0
    page_size: int = 0
    requests_count: int = 0
    compression_enabled: bool = False
    caching_enabled: bool = False
    cdn_detected: bool = False
    lighthouse_score: Optional[int] = None

@dataclass
class AsyncResponse:
    status: int
    headers: Dict
    body: bytes
    url: str
    elapsed: float
    content_type: str = ''
    encoding: str = 'utf-8'

@dataclass
class GraphQLResponse:
    data: Optional[Dict] = None
    errors: Optional[List[Dict]] = None
    extensions: Optional[Dict] = None

@dataclass
class AIScrapingResult:
    elements: List[Dict] = field(default_factory=list)
    confidence: float = 0.0
    model_used: str = ''
    processing_time: float = 0.0
    tokens_used: int = 0
    raw_response: Optional[str] = None

@dataclass
class CAPTCHAResult:
    solved: bool
    solution: Optional[str] = None
    provider: str = ''
    time_taken: float = 0.0
    cost: float = 0.0
    attempts: int = 1

@dataclass
class AIConfig:
    enabled: bool = False
    provider: str = 'deepseek'
    model: Optional[str] = None
    api_key: Optional[str] = None
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    total_timeout: float = 120.0
    max_cache_entries: int = 100
    cache_ttl_enabled: bool = False
    cache_ttl_seconds: int = 3600

@dataclass
class CheckerConfig:
    ssl_timeout: Optional[float] = None
    dns_timeout: Optional[float] = None
    port_timeout: Optional[float] = None
    ping_timeout: Optional[float] = None
    status_timeout: Optional[float] = None
    redirect_timeout: Optional[float] = None

@dataclass
class CaptchaConfig:
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    solve_timeout: float = 180.0

@dataclass
class CrawlerConfig:
    request_timeout: Optional[float] = 10.0
    delay: float = 0.3

@dataclass
class RobotsConfig:
    respect: bool = False
    user_agent: str = 'JWebs/2.0'
    timeout: Optional[float] = 5.0

@dataclass
class LoggingConfig:
    enabled: bool = False
    log_dir: str = 'logs'
    level: int = 20
    console: bool = True

@dataclass
class RateLimitConfig:
    requests_per_second: float = 0.0
    wait_timeout: float = 30.0

@dataclass
class AsyncConfig:
    timeout: Optional[float] = 30.0
    connect_timeout: Optional[float] = 10.0

@dataclass
class MonitorConfig:
    check_interval: int = 60
    check_timeout: Optional[float] = 10.0

@dataclass
class ProxyConfigGroup:
    enabled: bool = False

@dataclass
class ClientCertConfig:
    cert: Optional[str] = None
    key: Optional[str] = None
    password: Optional[str] = None
    ca_bundle: Optional[str] = None

@dataclass
class HTTPConfig:
    timeout: Optional[float] = None
    connect_timeout: Optional[float] = None
    num_pools: int = 20
    pool_maxsize: int = 50
    max_workers: int = 10
    default_headers: Optional[Dict] = None
    use_random_ua: bool = False
    ua_list: Optional[List[str]] = None
    referrer: Optional[str] = None
    verify_ssl: bool = True
    use_retry: bool = False
    retry_total: int = 3
    retry_backoff: float = 0.1
    retry_status_forcelist: Optional[List[int]] = None
    use_cache: bool = False
    cache_ttl: float = 300.0
    redirects: bool = False
    suppress_ssl_warnings: bool = True
    session_idle_timeout: Optional[float] = None
    allow_expired_sessions: bool = False
    auto_decompress: bool = True