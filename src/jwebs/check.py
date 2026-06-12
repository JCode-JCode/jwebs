# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .core.http import FastHTTP
from .core.datatypes import SecurityReport, SEOScore, PerformanceMetrics
from .core.constants import MAX_REDIRECT_HOPS
from .core.logging import logger


class Checker:
    def __init__(self, http: Optional[FastHTTP] = None,
                 ssl_timeout: float = 5.0, dns_timeout: float = 5.0,
                 port_timeout: float = 2.0, ping_timeout: float = 3.0,
                 status_timeout: float = 5.0, redirect_timeout: float = 5.0):
        self.http = http or FastHTTP()
        self.ssl_timeout = ssl_timeout
        self.dns_timeout = dns_timeout
        self.port_timeout = port_timeout
        self.ping_timeout = ping_timeout
        self.status_timeout = status_timeout
        self.redirect_timeout = redirect_timeout
        self._dns_cache: Dict[str, Dict] = {}
        self._ssl_cache: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = 300.0

    def set_timeouts(self, ssl: Optional[float] = None, dns: Optional[float] = None,
                     port: Optional[float] = None, ping: Optional[float] = None,
                     status: Optional[float] = None, redirect: Optional[float] = None):
        if ssl is not None: self.ssl_timeout = ssl
        if dns is not None: self.dns_timeout = dns
        if port is not None: self.port_timeout = port
        if ping is not None: self.ping_timeout = ping
        if status is not None: self.status_timeout = status
        if redirect is not None: self.redirect_timeout = redirect

    def _clean_ssl_cache(self):
        now = time.time()
        with self._cache_lock:
            expired = [host for host, entry in self._ssl_cache.items() if now - entry['timestamp'] > self._cache_ttl]
            for host in expired:
                del self._ssl_cache[host]

    def _clean_dns_cache(self):
        now = time.time()
        with self._cache_lock:
            expired = [host for host, entry in self._dns_cache.items() if now - entry['timestamp'] > self._cache_ttl]
            for host in expired:
                del self._dns_cache[host]

    def has_ssl(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return False
        try:
            resp = self.http.HEAD(url, timeout=self.ssl_timeout)
            return resp.status > 0
        except Exception:
            return False

    def get_ssl_info(self, url: str) -> Optional[Dict]:
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return None
        hostname = parsed.hostname
        port = parsed.port or 443
        try:
            import ssl
            import socket
            context = ssl.create_default_context()
            with socket.create_connection((hostname, port), timeout=self.ssl_timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    if not cert:
                        return None
                    issuer = dict(x[0] for x in cert.get('issuer', []))
                    subject = dict(x[0] for x in cert.get('subject', []))
                    not_before = cert.get('notBefore')
                    not_after = cert.get('notAfter')
                    san = [x[1] for x in cert.get('subjectAltName', [])]
                    return {
                        'issuer': issuer,
                        'subject': subject,
                        'version': cert.get('version'),
                        'serial': cert.get('serialNumber'),
                        'not_before': not_before,
                        'not_after': not_after,
                        'san': san,
                    }
        except Exception as e:
            logger.debug('Checker', f"get_ssl_info failed for {url}: {e}")
            return None

    def is_https(self, url: str) -> bool:
        return urlparse(url).scheme == 'https'

    def check_security_headers(self, url: str) -> Dict[str, bool]:
        try:
            resp = self.http.GET(url, timeout=self.status_timeout)
            if not resp or resp.status == 0:
                return {}
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return {
                'hsts': 'strict-transport-security' in headers,
                'x_frame_options': 'x-frame-options' in headers,
                'x_content_type_options': 'x-content-type-options' in headers,
                'x_xss_protection': 'x-xss-protection' in headers,
                'content_security_policy': 'content-security-policy' in headers,
                'referrer_policy': 'referrer-policy' in headers,
                'permissions_policy': 'permissions-policy' in headers,
            }
        except Exception as e:
            logger.error('Checker', f"Security headers check failed: {e}", exc_info=True)
            return {}

    def get_security_score(self, url: str) -> Tuple[int, Dict]:
        headers = self.check_security_headers(url)
        if not headers:
            return 0, {}
        score = sum(1 for v in headers.values() if v)
        max_score = len(headers)
        percentage = (score / max_score * 100) if max_score > 0 else 0
        return int(percentage), headers

    def get_dns_info(self, url: str) -> Optional[Dict]:
        self._clean_dns_cache()
        try:
            hostname = urlparse(url).hostname
            if not hostname:
                return None
            with self._cache_lock:
                if hostname in self._dns_cache:
                    entry = self._dns_cache[hostname]
                    if time.time() - entry['timestamp'] < self._cache_ttl:
                        return entry['info']
                    else:
                        del self._dns_cache[hostname]
            import socket
            import ipaddress
            socket.setdefaulttimeout(self.dns_timeout)
            ip = socket.gethostbyname(hostname)
            info = {
                'hostname': hostname, 'ip': ip,
                'is_ipv4': ipaddress.ip_address(ip).version == 4,
                'is_private': ipaddress.ip_address(ip).is_private,
                'is_loopback': ipaddress.ip_address(ip).is_loopback,
            }
            with self._cache_lock:
                self._dns_cache[hostname] = {'info': info, 'timestamp': time.time()}
            return info
        except Exception as e:
            logger.debug('Checker', f"DNS info failed for {url}: {e}")
            return None

    def check_port(self, host: str, port: int, timeout: Optional[float] = None) -> bool:
        timeout = timeout or self.port_timeout
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except socket.error:
            return False

    def is_up(self, url: str, timeout: Optional[float] = None) -> bool:
        timeout = timeout or self.status_timeout
        for attempt in range(2):
            try:
                resp = self.http.GET(url, timeout=timeout)
                if resp and 200 <= resp.status < 400:
                    return True
            except Exception:
                pass
            if attempt < 1:
                time.sleep(1)
        return False

    def is_down(self, url: str) -> bool:
        return not self.is_up(url)

    def ping(self, url: str, count: int = 3, timeout: Optional[float] = None) -> Dict:
        timeout = timeout or self.ping_timeout
        results = []
        for _ in range(count):
            start = time.time()
            resp = self.http.HEAD(url, timeout=timeout)
            ping_time = (time.time() - start) * 1000 if resp and resp.status > 0 else None
            results.append({
                'success': resp is not None and resp.status > 0,
                'time_ms': ping_time,
                'status': resp.status if resp and resp.status > 0 else None
            })
        successful_times = [r['time_ms'] for r in results if r['time_ms'] is not None]
        successful_count = len([r for r in results if r['success']])
        return {
            'results': results,
            'avg_time': sum(successful_times) / max(1, len(successful_times)),
            'packet_loss': (1 - successful_count / count) * 100,
            'min_time': min(successful_times) if successful_times else None,
            'max_time': max(successful_times) if successful_times else None
        }

    def analyze_redirects(self, url: str, timeout: Optional[float] = None) -> Dict:
        timeout = timeout or self.redirect_timeout
        chain = []
        current = url
        total_time = 0
        for _ in range(MAX_REDIRECT_HOPS):
            start = time.time()
            resp = self.http.GET(current, timeout=timeout, redirects=False)
            duration = time.time() - start
            total_time += duration
            if not resp or resp.status == 0:
                break
            chain.append({'url': current, 'status': resp.status, 'duration': duration})
            if resp.status in (301, 302, 303, 307, 308):
                location = resp.headers.get('Location', '') or resp.headers.get('location', '')
                if not location:
                    break
                from urllib.parse import urljoin
                current = urljoin(current, location)
            else:
                break
        return {
            'chain_length': len(chain),
            'total_time': total_time,
            'final_url': current,
            'redirect_type': 'permanent' if any(r['status'] == 301 for r in chain) else 'temporary',
            'hops': chain
        }

    def status_code(self, url: str, timeout: Optional[float] = None) -> Optional[int]:
        timeout = timeout or self.status_timeout
        try:
            resp = self.http.HEAD(url, timeout=timeout)
            return resp.status if resp and resp.status > 0 else None
        except Exception:
            return None

    def is_2xx(self, url: str) -> bool:
        code = self.status_code(url)
        return code is not None and 200 <= code < 300

    def is_3xx(self, url: str) -> bool:
        code = self.status_code(url)
        return code is not None and 300 <= code < 400

    def is_4xx(self, url: str) -> bool:
        code = self.status_code(url)
        return code is not None and 400 <= code < 500

    def is_5xx(self, url: str) -> bool:
        code = self.status_code(url)
        return code is not None and 500 <= code < 600

    def get_headers(self, url: str, timeout: Optional[float] = None) -> Dict:
        timeout = timeout or self.status_timeout
        try:
            resp = self.http.HEAD(url, timeout=timeout)
            return resp.headers if resp and resp.status > 0 else {}
        except Exception:
            return {}

    def security_audit(self, url: str) -> SecurityReport:
        report = SecurityReport(url=url)
        try:
            ssl_info = self.get_ssl_info(url)
            if ssl_info:
                report.ssl_valid = True
                report.ssl_issuer = ssl_info.get('issuer', {}).get('organizationName', 'Unknown')
                try:
                    report.ssl_expiry = datetime.strptime(
                        ssl_info['not_after'], '%b %d %H:%M:%S %Y %Z'
                    )
                except (ValueError, KeyError):
                    pass
            else:
                report.ssl_valid = self.has_ssl(url)
            report.security_headers = self.check_security_headers(url)
            if report.security_headers:
                score = sum(1 for v in report.security_headers.values() if v)
                max_score = len(report.security_headers)
                report.score = int((score / max_score) * 100) if max_score > 0 else 0
                grades = [(90, "A+"), (80, "A"), (70, "B"), (60, "C"), (50, "D")]
                report.grade = "F"
                for threshold, grade in grades:
                    if report.score >= threshold:
                        report.grade = grade
                        break
        except Exception as e:
            logger.error('Checker', f"Security audit failed: {e}", exc_info=True)
        return report

    def detect_tech(self, url: str) -> Dict[str, List[str]]:
        tech = {'frameworks': [], 'cms': [], 'server': [], 'analytics': []}
        try:
            resp = self.http.GET(url, timeout=self.status_timeout)
            if not resp or resp.status == 0:
                return tech
            headers = {k.lower(): v for k, v in resp.headers.items()}
            html = resp.text.lower() if resp.text else ''
            if 'server' in headers:
                tech['server'].append(headers['server'])
            if 'x-powered-by' in headers:
                tech['frameworks'].append(headers['x-powered-by'])
            if 'wp-content' in html:
                tech['cms'].append('WordPress')
            if 'drupal' in html:
                tech['cms'].append('Drupal')
            if 'joomla' in html:
                tech['cms'].append('Joomla')
            if 'google-analytics' in html or 'gtag' in html:
                tech['analytics'].append('Google Analytics')
        except Exception:
            pass
        return tech

    def is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def parse_url(self, url: str) -> Dict:
        parsed = urlparse(url)
        return {
            'scheme': parsed.scheme,
            'netloc': parsed.netloc,
            'path': parsed.path,
            'params': parsed.params,
            'query': parsed.query,
            'fragment': parsed.fragment,
            'hostname': parsed.hostname,
            'port': parsed.port,
        }

    def seo_audit(self, url: str) -> SEOScore:
        score = SEOScore()
        try:
            resp = self.http.GET(url, timeout=self.status_timeout)
            if not resp or resp.status == 0:
                score.recommendations.append("Page could not be fetched")
                return score
            soup = BeautifulSoup(resp.text, 'html.parser')
            title = soup.find('title')
            if title and title.string:
                score.on_page += 20
            else:
                score.recommendations.append("Missing title tag")
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                score.on_page += 15
            else:
                score.recommendations.append("Missing meta description")
            h1 = soup.find('h1')
            if h1:
                score.content += 10
            else:
                score.recommendations.append("Missing H1 tag")
            images = soup.find_all('img')
            if images:
                alt_count = sum(1 for img in images if img.get('alt'))
                score.content += int((alt_count / len(images)) * 15)
            if self.is_https(url):
                score.technical += 20
            else:
                score.recommendations.append("Not using HTTPS")
            score.overall = score.on_page + score.technical + score.content + score.mobile + score.speed
        except Exception as e:
            score.recommendations.append(f"Audit error: {e}")
        return score

    def performance_test(self, url: str, runs: int = 3) -> PerformanceMetrics:
        metrics = PerformanceMetrics()
        times = []
        for _ in range(runs):
            start = time.time()
            resp = self.http.GET(url, timeout=self.status_timeout)
            if resp and resp.status > 0:
                times.append(time.time() - start)
                if not metrics.page_size:
                    metrics.page_size = len(resp.data)
        if times:
            metrics.load_time = sum(times) / len(times)
            metrics.ttfb = times[0] * 0.3
            metrics.dom_complete = sum(times) / len(times)
        return metrics