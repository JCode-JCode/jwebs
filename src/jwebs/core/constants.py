# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import re

DEFAULT_CACHE_TTL = 300.0
DEFAULT_MEMORY_TTL = 300.0
MAX_MEMORY_ENTRIES = 1000
DEFAULT_ROBOTS_CACHE_TTL = 3600
DEFAULT_RATE_LIMIT = 0
DEFAULT_RATE_LIMIT_TIMEOUT = 30.0
DEFAULT_SESSION_IDLE_TIMEOUT = None
DEFAULT_NUM_POOLS = 20
DEFAULT_POOL_MAXSIZE = 50
DEFAULT_MAX_WORKERS = 10

DEFAULT_HTTP_TIMEOUT = None
DEFAULT_CONNECT_TIMEOUT = None

DEFAULT_CRAWLER_DELAY = 0.3

DEFAULT_MONITOR_INTERVAL = 60

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MAX_REDIRECT_HOPS = 15
CRAWLER_DEFAULT_DELAY = 0.3
MONITOR_DEFAULT_INTERVAL = 60

RE_EMAIL = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
RE_PHONE_PATTERNS = [
    re.compile(r'\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}'),
    re.compile(r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}'),
    re.compile(r'\(\d{3}\)\s*\d{3}[-.\s]?\d{4}'),
]
RE_PRICE_PATTERNS = [
    re.compile(r'[\$\u20ac\u00a3\u00a5]\s*\d+(?:[,.]\d{1,2})?'),
    re.compile(r'\d+(?:[,.]\d{1,2})?\s*[\$\u20ac\u00a3\u00a5]'),
]
RE_WORD = re.compile(r'\b\w+\b')