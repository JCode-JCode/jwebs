# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
class JWebsError(Exception):
    pass

class HTTPError(JWebsError):
    def __init__(self, message: str, status_code: int = None,
                 url: str = None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.response = response

class JWebsConnectionError(JWebsError):
    pass

class JWebsTimeoutError(JWebsError):
    pass

class RobotsBlockedError(JWebsError):
    def __init__(self, url: str):
        super().__init__(f"Blocked by robots.txt: {url}")
        self.url = url

class CacheError(JWebsError):
    pass