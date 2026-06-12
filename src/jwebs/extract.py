# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import json
import hashlib
import threading
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .core.http import FastHTTP
from .core.constants import RE_EMAIL, RE_PHONE_PATTERNS, RE_PRICE_PATTERNS
from .core.utils import _safe_parse_html
from .core.deps import _check_dep
from urllib.parse import urlparse
from .core.logging import logger

class Builder:
    def __init__(self, http: Optional[FastHTTP] = None):
        self.http = http or FastHTTP()
        self._soup_cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()

    def _make_cache_key(self, url: str, headers: Optional[Dict] = None) -> str:
        raw = url + (json.dumps(headers, sort_keys=True) if headers else '')
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_soup(self, url: str, headers: Optional[Dict] = None) -> Optional[BeautifulSoup]:
        key = self._make_cache_key(url, headers)
        with self._cache_lock:
            if key in self._soup_cache:
                entry = self._soup_cache[key]
                if time.time() - entry['time'] < 300:
                    return entry['soup']
                del self._soup_cache[key]
        resp = self.http.GET(url, headers=headers)
        if resp and resp.ok:
            soup = _safe_parse_html(resp.text, 'html.parser')
            with self._cache_lock:
                self._soup_cache[key] = {'soup': soup, 'time': time.time()}
            return soup
        return None

    def GET_TEXT(self, url: str, tag: str = 'p', headers: Optional[Dict] = None,
                limit: Optional[int] = None, min_length: int = 0) -> List[str]:
        soup = self._get_soup(url, headers)
        if not soup:
            return []
        elements = soup.find_all(tag, limit=limit) if limit else soup.find_all(tag)
        texts = [el.get_text(strip=True) for el in elements]
        if min_length > 0:
            texts = [t for t in texts if len(t) >= min_length]
        return texts

    def GET_ALL_TEXT(self, url: str, headers: Optional[Dict] = None,
                    clean: bool = True) -> str:
        soup = self._get_soup(url, headers)
        if not soup:
            return ''
        if clean:
            for element in soup(['script', 'style', 'noscript', 'iframe']):
                element.decompose()
        return soup.get_text(separator='\n', strip=True)

    def GET_TITLE(self, url: str, headers: Optional[Dict] = None) -> Optional[str]:
        soup = self._get_soup(url, headers)
        if not soup:
            return None
        title = soup.find('title')
        return title.get_text(strip=True) if title else None

    def GET_LINKS(self, url: str, internal: bool = False, external: bool = False,
                 nofollow: bool = False, headers: Optional[Dict] = None,
                 unique: bool = True) -> List[str]:
        soup = self._get_soup(url, headers)
        if not soup:
            return []
        domain = urlparse(url).netloc
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith(('#', 'javascript:', 'mailto:')):
                continue
            full_url = urljoin(url, href)
            is_internal = urlparse(full_url).netloc == domain
            if nofollow:
                rel = a.get('rel', '')
                if isinstance(rel, list):
                    rel = ' '.join(rel)
                if 'nofollow' in rel:
                    links.append(full_url)
                continue
            if internal and is_internal:
                links.append(full_url)
            elif external and not is_internal:
                links.append(full_url)
            elif not internal and not external:
                links.append(full_url)
        return list(set(links)) if unique else links

    def GET_IMAGES(self, url: str, headers: Optional[Dict] = None) -> List[Dict]:
        soup = self._get_soup(url, headers)
        if not soup:
            return []
        images = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            data_src = img.get('data-src', '')
            images.append({
                'src': urljoin(url, data_src or src),
                'alt': img.get('alt', ''),
                'title': img.get('title', ''),
                'loading': img.get('loading', 'auto'),
            })
        return images

    def GET_METAS(self, url: str, headers: Optional[Dict] = None) -> List[Dict]:
        soup = self._get_soup(url, headers)
        if not soup:
            return []
        return [{
            'name': m.get('name', ''),
            'property': m.get('property', ''),
            'content': m.get('content', ''),
        } for m in soup.find_all('meta')]

    def GET_META_DESC(self, url: str, headers: Optional[Dict] = None) -> Optional[str]:
        soup = self._get_soup(url, headers)
        if not soup:
            return None
        meta = soup.find('meta', attrs={'name': 'description'})
        return meta.get('content') if meta else None

    def GET_JSONLD(self, url: str, headers: Optional[Dict] = None) -> List[Dict]:
        soup = self._get_soup(url, headers)
        if not soup:
            return []
        jsonld = []
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                if script.string:
                    jsonld.append(json.loads(script.string))
            except (json.JSONDecodeError, ValueError):
                pass
        return jsonld

    def EXTRACT_EMAILS(self, url: str, headers: Optional[Dict] = None) -> List[str]:
        text = str(self._get_soup(url, headers) or '')
        return list(set(RE_EMAIL.findall(text)))

    def EXTRACT_PHONES(self, url: str, headers: Optional[Dict] = None) -> List[str]:
        text = str(self._get_soup(url, headers) or '')
        phones = []
        for pattern in RE_PHONE_PATTERNS:
            phones.extend(pattern.findall(text))
        return list(set(phones))

    def EXTRACT_PRICES(self, url: str, headers: Optional[Dict] = None) -> List[Dict]:
        text = self.GET_ALL_TEXT(url, headers)
        if not text:
            return []
        prices = []
        for pattern in RE_PRICE_PATTERNS:
            prices.extend([{'raw': m} for m in pattern.findall(text)])
        return prices

    def SENTIMENT(self, text: str) -> Dict:
        if not _check_dep('vaderSentiment'):
            return {'error': 'Install vaderSentiment: pip install vaderSentiment'}
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        scores = analyzer.polarity_scores(text)
        compound = scores['compound']
        return {
            'polarity': compound,
            'label': 'positive' if compound > 0.05 else 'negative' if compound < -0.05 else 'neutral',
            'pos_score': scores['pos'],
            'neu_score': scores['neu'],
            'neg_score': scores['neg']
        }

    def TRANSLATE(self, text: str, target_lang: str = 'en') -> str:
        if not _check_dep('deep_translator'):
            return text
        try:
            from deep_translator import GoogleTranslator
            return GoogleTranslator(target=target_lang).translate(text)
        except Exception as e:
            logger.error('Builder', f"Translation failed: {e}")
            return text

    def GET_HEADINGS(self, url: str, headers: Optional[Dict] = None) -> Dict[str, List[str]]:
        soup = self._get_soup(url, headers)
        if not soup:
            return {}
        return {
            h: [el.get_text(strip=True) for el in soup.find_all(h)]
            for h in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6')
        }

    def GET_SOCIAL(self, url: str, headers: Optional[Dict] = None) -> Dict[str, List[str]]:
        soup = self._get_soup(url, headers)
        if not soup:
            return {}
        social = {}
        platforms = {
            'facebook': ['facebook.com', 'fb.com'],
            'twitter': ['twitter.com', 'x.com'],
            'instagram': ['instagram.com'],
            'linkedin': ['linkedin.com'],
            'youtube': ['youtube.com', 'youtu.be'],
            'github': ['github.com'],
            'telegram': ['telegram.me', 't.me'],
            'reddit': ['reddit.com'],
        }
        for a in soup.find_all('a', href=True):
            href = a['href'].lower()
            for platform, domains in platforms.items():
                if any(d in href for d in domains):
                    if platform not in social:
                        social[platform] = []
                    social[platform].append(a['href'])
        return social

    def TO_JSON(self, data: Any, filepath: str, pretty: bool = True) -> str:
        with open(filepath, 'w', encoding='utf-8') as f:
            if pretty:
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                json.dump(data, f, ensure_ascii=False)
        return filepath

    def TO_CSV(self, data: List[Dict], filepath: str) -> str:
        import csv
        if not data:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('')
            return filepath
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return filepath
