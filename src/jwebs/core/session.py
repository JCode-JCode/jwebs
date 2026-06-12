# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import hashlib
import threading
import time
from typing import Dict, Optional

from .constants import DEFAULT_SESSION_IDLE_TIMEOUT

class SessionManager:
    def __init__(self, idle_timeout: float = DEFAULT_SESSION_IDLE_TIMEOUT):
        self.sessions: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self.idle_timeout = idle_timeout

    def create_session(self, name: str, base_url: str) -> str:
        session_id = hashlib.md5(f"{name}{base_url}{time.time()}".encode()).hexdigest()
        with self._lock:
            self.sessions[session_id] = {
                'name': name, 'base_url': base_url,
                'cookies': {}, 'headers': {},
                'created': time.time(), 'last_used': time.time()
            }
        return session_id

    def get_cookies(self, session_id: str) -> Dict:
        session = self.sessions.get(session_id, {})
        if session:
            if self.idle_timeout is not None:
                if time.time() - session.get('last_used', 0) > self.idle_timeout:
                    self.remove_session(session_id)
                    return {}
            return session.get('cookies', {})
        return {}

    def set_cookies(self, session_id: str, cookies: Dict):
        with self._lock:
            if session_id in self.sessions:
                self.sessions[session_id]['cookies'].update(cookies)
                self.sessions[session_id]['last_used'] = time.time()

    def update_from_response(self, session_id: str, response_headers: Dict):
        set_cookie = response_headers.get('Set-Cookie', '') or response_headers.get('set-cookie', '')
        if not set_cookie:
            return
        cookies = {}
        for cookie_part in set_cookie.split(';'):
            cookie_part = cookie_part.strip()
            if '=' in cookie_part:
                key, value = cookie_part.split('=', 1)
                if key.lower() not in ('path', 'domain', 'expires', 'max-age',
                                       'secure', 'httponly', 'samesite'):
                    cookies[key] = value
        if cookies:
            self.set_cookies(session_id, cookies)

    def get_session(self, session_id: str) -> Optional[Dict]:
        session = self.sessions.get(session_id)
        if session:
            if self.idle_timeout is not None:
                if time.time() - session.get('last_used', 0) > self.idle_timeout:
                    self.remove_session(session_id)
                    return None
            return session
        return None

    def remove_session(self, session_id: str):
        with self._lock:
            self.sessions.pop(session_id, None)

    def cleanup_idle_sessions(self):
        if self.idle_timeout is None:
            return
        with self._lock:
            now = time.time()
            idle = [sid for sid, s in self.sessions.items()
                    if now - s.get('last_used', 0) > self.idle_timeout]
            for sid in idle:
                del self.sessions[sid]

    def clear(self):
        with self._lock:
            self.sessions.clear()