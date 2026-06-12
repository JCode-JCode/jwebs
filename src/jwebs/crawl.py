# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import time
import threading
import json
from collections import deque
from typing import Dict, Set, Optional, List, Any
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from .core.http import FastHTTP
from .core.constants import CRAWLER_DEFAULT_DELAY
from .core.logging import logger
from .core.utils import _safe_parse_html


class Crawler:
    def __init__(self, http: Optional[FastHTTP] = None, request_timeout: float = 10.0,
                 delay: float = CRAWLER_DEFAULT_DELAY):
        self.http = http or FastHTTP(rate_limit=2.0, timeout=request_timeout)
        self.request_timeout = request_timeout
        self.delay = delay
        self.visited: Set[str] = set()
        self.results: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def CRAWL(self, start_url: str, max_depth: int = 3, max_pages: int = 100,
              same_domain: bool = True, delay: Optional[float] = None) -> Dict[str, Dict]:
        effective_delay = delay if delay is not None else self.delay
        queue = deque([(start_url, 0)])
        start_domain = urlparse(start_url).netloc

        while queue and len(self.visited) < max_pages:
            url, depth = queue.popleft()
            with self._lock:
                if url in self.visited or depth > max_depth:
                    continue
                self.visited.add(url)

            try:
                resp = self.http.GET(url, timeout=self.request_timeout)
                title = ''
                links = []
                if resp and resp.ok:
                    soup = BeautifulSoup(resp.data, 'html.parser')
                    title = soup.title.string if soup.title else ''
                    if depth < max_depth:
                        for a in soup.find_all('a', href=True):
                            href = a['href']
                            full_url = urljoin(url, href)
                            if same_domain and urlparse(full_url).netloc != start_domain:
                                continue
                            links.append(full_url)

                page_data = {
                    'url': url, 'depth': depth, 'title': title,
                    'links': links[:20], 'status': resp.status if resp else 0
                }
                with self._lock:
                    self.results[url] = page_data

                for link in links:
                    with self._lock:
                        if link not in self.visited:
                            queue.append((link, depth + 1))
            except Exception as e:
                with self._lock:
                    self.results[url] = {'url': url, 'depth': depth, 'error': str(e)}

            time.sleep(effective_delay)

        return self.results

    def CLEAR(self):
        with self._lock:
            self.visited.clear()
            self.results.clear()


class DistributedCrawler:
    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 queue_name: str = "jwebs:crawl:tasks",
                 visited_set: str = "jwebs:crawl:visited",
                 result_hash: str = "jwebs:crawl:results",
                 http: Optional[FastHTTP] = None,
                 request_timeout: float = 10.0,
                 respect_robots: bool = False):
        try:
            import redis
        except ImportError:
            raise ImportError("redis library is required for DistributedCrawler. "
                              "Install with: pip install redis")

        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.queue_name = queue_name
        self.visited_set = visited_set
        self.result_hash = result_hash
        self.request_timeout = request_timeout
        self.respect_robots = respect_robots
        self.http = http or FastHTTP(timeout=request_timeout,
                                     respect_robots_txt=respect_robots)

    def add_seed(self, url: str, depth: int = 0) -> None:
        task = json.dumps({"url": url, "depth": depth})
        self.redis.lpush(self.queue_name, task)
        logger.info("DistributedCrawler", f"Added seed: {url} (depth={depth})")

    def get_task(self, timeout: int = 5) -> Optional[Dict[str, Any]]:
        item = self.redis.brpop(self.queue_name, timeout=timeout)
        if item is None:
            return None
        _, task_json = item
        return json.loads(task_json)

    def save_result(self, url: str, data: Dict) -> None:
        self.redis.hset(self.result_hash, url, json.dumps(data, ensure_ascii=False))

    def get_result(self, url: str) -> Optional[Dict]:
        raw = self.redis.hget(self.result_hash, url)
        if raw:
            return json.loads(raw)
        return None

    def get_all_results(self) -> Dict[str, Dict]:
        items = self.redis.hgetall(self.result_hash)
        return {url: json.loads(data) for url, data in items.items()}

    def crawl_worker(self, max_pages: Optional[int] = None,
                     max_depth: int = 3,
                     same_domain: bool = True,
                     delay: float = 0.2,
                     on_result=None,
                     strict_page_limit: bool = False) -> None:
        crawled = 0
        successful_count = 0
        while True:
            if max_pages is not None:
                if strict_page_limit:
                    if successful_count >= max_pages:
                        break
                else:
                    if crawled >= max_pages:
                        break

            task = self.get_task(timeout=2)
            if task is None:
                break

            url = task["url"]
            depth = task["depth"]
            if depth > max_depth:
                continue

            if self.redis.sismember(self.visited_set, url):
                continue

            self.redis.sadd(self.visited_set, url)

            try:
                resp = self.http.GET(url, timeout=self.request_timeout)
                if not resp or resp.status == 0:
                    error_data = {
                        "url": url, "depth": depth, "error": "Failed to fetch",
                        "status": 0, "timestamp": time.time()
                    }
                    self.save_result(url, error_data)
                    if on_result:
                        on_result(url, error_data)
                    crawled += 1
                    continue

                soup = _safe_parse_html(resp.text, "html.parser")
                title = soup.title.string.strip() if soup.title else ""

                links = []
                if depth < max_depth:
                    domain = urlparse(url).netloc
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if not href or href.startswith(("#", "javascript:", "mailto:")):
                            continue
                        full_url = urljoin(url, href)
                        if same_domain:
                            if urlparse(full_url).netloc != domain:
                                continue
                        if self.redis.sadd(self.visited_set, full_url):
                            new_task = json.dumps({"url": full_url, "depth": depth + 1})
                            self.redis.lpush(self.queue_name, new_task)
                        links.append(full_url)

                result = {
                    "url": url,
                    "depth": depth,
                    "title": title,
                    "links": links[:50],
                    "status": resp.status,
                    "timestamp": time.time()
                }
                self.save_result(url, result)
                if on_result:
                    on_result(url, result)

                crawled += 1
                successful_count += 1
                logger.info("DistributedCrawler", f"Crawled {url} (total attempts={crawled}, stored={successful_count})")
                time.sleep(delay)

            except Exception as e:
                error_result = {
                    "url": url,
                    "depth": depth,
                    "error": str(e),
                    "timestamp": time.time()
                }
                self.save_result(url, error_result)
                if on_result:
                    on_result(url, error_result)
                crawled += 1
                logger.error("DistributedCrawler", f"Failed to crawl {url}: {e}")

    def clear(self) -> None:
        self.redis.delete(self.queue_name, self.visited_set, self.result_hash)

    def get_stats(self) -> Dict:
        return {
            "queue_length": self.redis.llen(self.queue_name),
            "visited_count": self.redis.scard(self.visited_set),
            "results_count": self.redis.hlen(self.result_hash)
        }

    def CLOSE(self) -> None:
        self.redis.close()