# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import os
import json
import hashlib
import threading
import time
import re
from typing import Dict, List, Optional, Any

from urllib3 import PoolManager, Timeout as Urllib3Timeout, Retry

from .core.http import FastHTTP
from .core.datatypes import AIScrapingResult, GraphQLResponse
from .core.utils import _safe_parse_html
from .core.deps import _check_dep
from .core.logging import logger

class AIScrapingEngine:
    def __init__(self, provider: str = 'deepseek', model: Optional[str] = None,
                 api_key: Optional[str] = None, use_local: bool = False,
                 connect_timeout: float = 10.0, read_timeout: float = 60.0,
                 total_timeout: float = 120.0,
                 max_cache_entries: int = 100, cache_ttl_enabled: bool = False,
                 cache_ttl_seconds: int = 3600):
        self.provider = provider.lower()
        if self.provider not in ('deepseek', 'openai'):
            raise ValueError("provider must be 'deepseek' or 'openai'")

        if self.provider == 'deepseek':
            self.base_url = "https://api.deepseek.com/v1/chat/completions"
            self.model = model or 'deepseek-chat'
            self.api_key = api_key or os.environ.get('DEEPSEEK_API_KEY', '')
        else:
            self.base_url = "https://api.openai.com/v1/chat/completions"
            self.model = model or 'gpt-4o'
            self.api_key = api_key or os.environ.get('OPENAI_API_KEY', '')

        self.use_local = use_local
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.total_timeout = total_timeout

        self.max_cache_entries = max_cache_entries
        self.cache_ttl_enabled = cache_ttl_enabled
        self.cache_ttl_seconds = cache_ttl_seconds

        self._ai_cache: Dict[str, AIScrapingResult] = {}
        self._cache_lock = threading.Lock()

        self._api_pool = PoolManager(
            num_pools=2,
            maxsize=5,
            timeout=Urllib3Timeout(connect=connect_timeout, read=read_timeout),
            retries=Retry(total=2, backoff_factor=0.5),
            cert_reqs='CERT_REQUIRED'
        )

        if not self.api_key:
            logger.warning('AIScrapingEngine',
                          f'No API key found for {self.provider}. Set environment variable accordingly.')

    def set_timeouts(self, connect: Optional[float] = None, read: Optional[float] = None,
                     total: Optional[float] = None):
        if connect is not None:
            self.connect_timeout = connect
        if read is not None:
            self.read_timeout = read
        if total is not None:
            self.total_timeout = total
        self._api_pool = PoolManager(
            num_pools=2, maxsize=5,
            timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout),
            retries=Retry(total=2, backoff_factor=0.5),
            cert_reqs='CERT_REQUIRED'
        )

    def _call_llm(self, messages: List[Dict], temperature: float = 0.1,
                  max_tokens: int = 2000) -> Optional[Dict]:
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'stream': False
        }

        try:
            response = self._api_pool.request(
                'POST', self.base_url,
                body=json.dumps(payload).encode('utf-8'),
                headers=headers,
                timeout=Urllib3Timeout(connect=self.connect_timeout, read=self.read_timeout)
            )

            if response.status == 200:
                data = json.loads(response.data.decode('utf-8'))
                response.release_conn()
                return data
            else:
                logger.error('AIScrapingEngine', f"{self.provider} API error: {response.status}")
                response.release_conn()
                return None
        except Exception as e:
            logger.error('AIScrapingEngine', f"{self.provider} API call failed: {e}", exc_info=True)
            return None

    def _prune_cache(self):
        with self._cache_lock:
            now = time.time()
            if self.cache_ttl_enabled:
                expired = [k for k, v in self._ai_cache.items()
                           if now - v.processing_time > self.cache_ttl_seconds]
                for k in expired:
                    del self._ai_cache[k]
            if len(self._ai_cache) > self.max_cache_entries:
                sorted_items = sorted(self._ai_cache.items(), key=lambda x: x[1].processing_time)
                to_remove = len(self._ai_cache) - self.max_cache_entries
                for k, _ in sorted_items[:to_remove]:
                    del self._ai_cache[k]

    def _extract_single(self, text: str, instruction: str, start_time: float) -> AIScrapingResult:
        cache_key = hashlib.md5(f"{self.provider}{self.model}{instruction}{text[:2000]}".encode()).hexdigest()
        with self._cache_lock:
            if cache_key in self._ai_cache:
                cached = self._ai_cache[cache_key]
                if not self.cache_ttl_enabled or (time.time() - cached.processing_time <= self.cache_ttl_seconds):
                    return cached
                else:
                    del self._ai_cache[cache_key]

        system_prompt = """You are a precise data extraction assistant. 
Extract information exactly as requested. Always return valid JSON.
If information is not found, use null values. Never make up data."""

        user_prompt = f"""Extract the following information from the text:

TEXT:
{text}

INSTRUCTION:
{instruction}

Return ONLY a valid JSON object. Do not include explanations or markdown."""

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        response_data = self._call_llm(messages)

        if not response_data:
            return AIScrapingResult(
                elements=[{'error': 'API call failed'}],
                model_used=self.model,
                processing_time=time.time() - start_time
            )

        try:
            result_text = response_data['choices'][0]['message']['content']
            tokens_used = response_data.get('usage', {}).get('total_tokens', 0)
            data = self._parse_json_safely(result_text)

            result = AIScrapingResult(
                elements=data if isinstance(data, list) else [data],
                confidence=0.9,
                model_used=self.model,
                processing_time=time.time() - start_time,
                tokens_used=tokens_used,
                raw_response=result_text
            )

            with self._cache_lock:
                self._ai_cache[cache_key] = result
                self._prune_cache()

            return result
        except Exception as e:
            logger.error('AIScrapingEngine', f"Parse error: {e}", exc_info=True)
            return AIScrapingResult(
                elements=[{'error': f'Parse error: {str(e)}'}],
                model_used=self.model,
                processing_time=time.time() - start_time
            )

    def EXTRACT(self, html: str, instruction: str) -> AIScrapingResult:
        start_time = time.time()

        soup = _safe_parse_html(html, 'lxml')
        for tag in soup(['script', 'style', 'noscript', 'iframe', 'nav', 'footer']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)

        if len(text) <= 8000:
            return self._extract_single(text, instruction, start_time)
        else:
            return self._extract_chunks(text, instruction, start_time)

    def _extract_chunks(self, text: str, instruction: str, start_time: float) -> AIScrapingResult:
        chunk_size = 6000
        overlap = 500
        chunks = []
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i:i + chunk_size]
            if len(chunk) > 100:
                chunks.append(chunk)

        if not chunks:
            return AIScrapingResult(elements=[{'error': 'No valid text found'}])

        all_elements = []
        total_tokens = 0
        for idx, chunk in enumerate(chunks):
            if idx == 0:
                chunk_result = self._extract_single(chunk, instruction, start_time)
            else:
                prev_context = json.dumps(all_elements[-1] if all_elements else {})
                enhanced_instruction = f"{instruction}\n\nPrevious findings: {prev_context}"
                chunk_result = self._extract_single(chunk, enhanced_instruction, start_time)

            if chunk_result.elements:
                if isinstance(chunk_result.elements, list):
                    all_elements.extend(chunk_result.elements)
                else:
                    all_elements.append(chunk_result.elements)
                total_tokens += chunk_result.tokens_used

        return AIScrapingResult(
            elements=all_elements,
            confidence=0.85,
            model_used=self.model,
            processing_time=time.time() - start_time,
            tokens_used=total_tokens
        )

    def _parse_json_safely(self, text: str) -> Any:
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        json_match = re.search(r'\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {'raw_output': text}

    def SUMMARIZE(self, text: str, max_length: int = 150) -> str:
        if len(text) < 100:
            return text

        text = text[:8000]
        messages = [
            {'role': 'system', 'content': "You are a text summarization expert."},
            {'role': 'user', 'content': f"Summarize in {max_length} chars:\n\n{text}"}
        ]

        response = self._call_llm(messages, temperature=0.3, max_tokens=max_length)
        if response:
            return response['choices'][0]['message']['content'].strip()

        sentences = text.split('.')[:5]
        return '. '.join(sentences) + '.'

    def SCRAPE_PAGE(self, url: str, instruction: str,
                   http: Optional[FastHTTP] = None) -> AIScrapingResult:
        client = http or FastHTTP()
        resp = client.GET(url)
        if not resp or resp.status == 0:
            return AIScrapingResult(elements=[{'error': f'Failed to fetch URL: {url}'}])
        return self.EXTRACT(resp.text, instruction)

    def SET_API_KEY(self, api_key: str):
        self.api_key = api_key

    def CLEAR_CACHE(self):
        with self._cache_lock:
            self._ai_cache.clear()


class GraphQLClient:
    def __init__(self, endpoint: str, headers: Optional[Dict] = None,
                 timeout: float = 30.0, http: Optional[FastHTTP] = None):
        self.endpoint = endpoint
        self.headers = headers or {'Content-Type': 'application/json'}
        self.timeout = timeout
        self.http = http or FastHTTP()

    def QUERY(self, query: str, variables: Optional[Dict] = None) -> GraphQLResponse:
        payload = {'query': query}
        if variables:
            payload['variables'] = variables
        resp = self.http.POST(
            self.endpoint, json_data=payload,
            headers=self.headers, timeout=self.timeout
        )
        if resp and resp.ok:
            data = resp.JSON()
            if data:
                return GraphQLResponse(
                    data=data.get('data'),
                    errors=data.get('errors'),
                    extensions=data.get('extensions')
                )
        return GraphQLResponse(
            errors=[{'message': f'HTTP {resp.status if resp else "error"}'}]
        )