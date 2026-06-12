# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import threading
import time

class RateLimiter:
    def __init__(self, requests_per_second: float = 0,
                 wait_timeout: float = 30.0):
        self.wait_timeout = wait_timeout
        self.lock = threading.Lock()
        self._enabled = requests_per_second > 0
        if self._enabled:
            self.rate = requests_per_second
            self.tokens = requests_per_second
            self.max_tokens = requests_per_second
        else:
            self.rate = 0
            self.tokens = 0
            self.max_tokens = 0
        self.last_update = time.monotonic()

    def acquire(self) -> bool:
        if not self._enabled:
            return True
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
            self.last_update = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    def wait_and_acquire(self, timeout: float = None) -> bool:
        if timeout is None:
            timeout = self.wait_timeout
        if timeout is None:
            while not self.acquire():
                time.sleep(0.01)
            return True
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.acquire():
                return True
            time.sleep(0.001)
        return False

    def set_rate(self, requests_per_second: float):
        with self.lock:
            self._enabled = requests_per_second > 0
            if self._enabled:
                self.rate = requests_per_second
                self.max_tokens = requests_per_second
                self.tokens = min(self.tokens, self.max_tokens)
            else:
                self.rate = 0
                self.max_tokens = 0
                self.tokens = 0

    def set_wait_timeout(self, timeout: float):
        self.wait_timeout = timeout