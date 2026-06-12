# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from .core.http import FastHTTP
from .core.constants import RE_EMAIL, RE_PHONE_PATTERNS
from .core.utils import _safe_parse_html
from .core.logging import logger
from .check import Checker
from .extract import Builder
from .ai import AIScrapingEngine
from .captcha import CaptchaSolver
from .proxy import ProxyRotator
from .diff import ContentDiffer

class SmartScraper:
    def __init__(self, use_ai: bool = False, use_proxy: bool = False,
                 respect_robots: bool = False, http: Optional[FastHTTP] = None):
        self.http = http or FastHTTP(
            enable_logging=False, respect_robots_txt=respect_robots,
            log_level=logging.WARNING
        )
        self.checker = Checker(self.http)
        self.builder = Builder(self.http)
        self.differ = ContentDiffer()
        self.use_ai = use_ai
        self.use_proxy = use_proxy
        self.ai_engine = AIScrapingEngine() if use_ai else None
        self.proxy_rotator = ProxyRotator() if use_proxy else None
        self.captcha_solver = CaptchaSolver()
        self._stats = {'pages_scraped': 0, 'start_time': time.time()}
        self._lock = threading.Lock()

    def _scrape_with_http(self, url: str, instruction: Optional[str] = None,
                          http: Optional[FastHTTP] = None) -> Dict:
        http = http or self.http
        checker = Checker(http)
        builder = Builder(http)
        result = {'url': url, 'timestamp': time.time(), 'success': False, 'data': {}, 'metadata': {}}
        try:
            resp = http.GET(url)
            html = resp.text if resp and resp.status > 0 else ''
            if not html:
                result['error'] = 'Failed to fetch page'
                return result

            captcha_type = self.captcha_solver.DETECT(html)
            if captcha_type:
                result['metadata']['captcha_detected'] = captcha_type

            soup = _safe_parse_html(html, 'html.parser')

            if instruction and self.ai_engine:
                ai_result = self.ai_engine.EXTRACT(html, instruction)
                result['data'] = ai_result.elements[0] if ai_result.elements else {}
            else:
                title = soup.title.string.strip() if soup.title else ''
                text = soup.get_text(separator='\n', strip=True)[:2000]
                links = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if not href.startswith(('#', 'javascript:', 'mailto:')):
                        from urllib.parse import urljoin
                        links.append(urljoin(url, href))
                emails = list(set(RE_EMAIL.findall(html)))
                phones = []
                for pattern in RE_PHONE_PATTERNS:
                    phones.extend(pattern.findall(html))
                phones = list(set(phones))

                result['data'] = {
                    'title': title,
                    'text': text,
                    'links': links[:20],
                    'emails': emails,
                    'phones': phones
                }

            result['metadata'].update({
                'status_code': resp.status if resp else None,
                'ssl_valid': checker.has_ssl(url),
            })
            result['success'] = True
            with self._lock:
                self._stats['pages_scraped'] += 1
        except Exception as e:
            result['error'] = str(e)
            logger.error('SmartScraper', f"Scraping failed for {url}: {e}", exc_info=True)
        return result

    def SCRAPE(self, url: str, instruction: Optional[str] = None) -> Dict:
        return self._scrape_with_http(url, instruction, self.http)

    def SCRAPE_MULTI(self, urls: List[str], instruction: Optional[str] = None,
                    max_concurrent: int = 5) -> Dict[str, Dict]:
        results = {}
        def scrape_one(url):
            http = FastHTTP(
                use_random_ua=self.http.use_random_ua,
                ua_list=self.http._ua_list,
                referrer=self.http.referrer,
                verify_ssl=self.http.verify_ssl,
                use_retry=self.http.use_retry,
                retry_total=self.http.retry_total,
                retry_backoff=self.http.retry_backoff,
                retry_status_forcelist=self.http.retry_status_forcelist,
                timeout=self.http.read_timeout,
                connect_timeout=self.http.connect_timeout,
                use_cache=False,
                respect_robots_txt=self.http.respect_robots,
                robots_user_agent=self.http._robots_user_agent,
                rate_limit=0,
            )
            return self._scrape_with_http(url, instruction, http)

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            future_to_url = {executor.submit(scrape_one, url): url for url in urls}
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    results[url] = {'url': url, 'success': False, 'error': str(e)}
        return results