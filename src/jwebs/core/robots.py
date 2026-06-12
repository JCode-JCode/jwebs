# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import re
import threading
import time
from urllib.parse import urlparse
from typing import Dict, List, Optional
from urllib3 import PoolManager, Timeout as Urllib3Timeout

from .logging import logger
from .constants import DEFAULT_ROBOTS_CACHE_TTL

class RobotsParser:
    def __init__(self, user_agent: str = 'JWebs/2.0', timeout: float = 5.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self._robots_cache: Dict[str, Dict] = {}
        self._cache_ttl = DEFAULT_ROBOTS_CACHE_TTL
        self._lock = threading.Lock()
        self._pool = PoolManager(
            num_pools=2, maxsize=5,
            timeout=Urllib3Timeout(connect=5.0, read=timeout)
        )

    def set_user_agent(self, user_agent: str):
        self.user_agent = user_agent

    def set_timeout(self, timeout: float):
        self.timeout = timeout
        self._pool = PoolManager(
            num_pools=2, maxsize=5,
            timeout=Urllib3Timeout(connect=5.0, read=timeout)
        )

    def _fetch(self, base_url: str) -> Optional[str]:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        with self._lock:
            if robots_url in self._robots_cache:
                cache_entry = self._robots_cache[robots_url]
                if time.time() - cache_entry['timestamp'] < self._cache_ttl:
                    return cache_entry['content']
        try:
            resp = self._pool.request(
                'GET', robots_url,
                timeout=Urllib3Timeout(connect=5.0, read=self.timeout)
            )
            if resp and resp.status == 200:
                content = resp.data.decode('utf-8', errors='ignore')
                resp.release_conn()
                with self._lock:
                    self._robots_cache[robots_url] = {'content': content, 'timestamp': time.time()}
                return content
            else:
                if resp:
                    resp.release_conn()
                with self._lock:
                    self._robots_cache[robots_url] = {'content': None, 'timestamp': time.time()}
                return None
        except Exception as e:
            logger.warning('RobotsParser', f"Failed to fetch robots.txt: {e}")
            return None

    def _parse(self, content: str) -> Dict:
        rules = {'allow': [], 'disallow': [], 'crawl_delay': None, 'sitemaps': []}
        if not content:
            return rules
        current_agents = []
        for line in content.split('\n'):
            line = line.split('#')[0].strip()
            if not line or ':' not in line:
                continue
            key, value = line.split(':', 1)
            key = key.strip().lower()
            value = value.strip()
            if key == 'user-agent':
                current_agents.append(value.lower())
            elif current_agents:
                is_applicable = '*' in current_agents or self.user_agent.lower() in current_agents
                if is_applicable:
                    if key == 'disallow' and value:
                        rules['disallow'].append(value)
                    elif key == 'allow' and value:
                        rules['allow'].append(value)
                    elif key == 'crawl-delay':
                        try:
                            rules['crawl_delay'] = float(value)
                        except ValueError:
                            pass
            if key == 'sitemap' and value:
                rules['sitemaps'].append(value)
        rules['allow'].sort(key=len, reverse=True)
        rules['disallow'].sort(key=len, reverse=True)
        return rules

    def is_allowed(self, url: str) -> bool:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path or '/'
        robots_content = self._fetch(url)
        if robots_content is None:
            return True
        rules = self._parse(robots_content)
        for allow_path in rules['allow']:
            if self._path_matches(path, allow_path):
                return True
        for disallow_path in rules['disallow']:
            if self._path_matches(path, disallow_path):
                return False
        return True

    def _path_matches(self, path: str, rule: str) -> bool:
        if not rule:
            return False
        rule_escaped = re.escape(rule)
        rule_pattern_str = rule_escaped.replace(r'\*', '.*')
        if rule.endswith('$'):
            rule_pattern_str = rule_pattern_str[:-2] + '$'
        rule_pattern = re.compile(rule_pattern_str)
        return bool(rule_pattern.match(path))

    def get_crawl_delay(self, url: str) -> Optional[float]:
        robots_content = self._fetch(url)
        if robots_content is None:
            return None
        return self._parse(robots_content)['crawl_delay']

    def get_sitemaps(self, url: str) -> List[str]:
        robots_content = self._fetch(url)
        if robots_content is None:
            return []
        return self._parse(robots_content)['sitemaps']

    def clear_cache(self):
        with self._lock:
            self._robots_cache.clear()
        self._pool.clear()