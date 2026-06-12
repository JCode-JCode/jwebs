# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import time
import threading
from typing import List, Dict, Optional

from .core.datatypes import ProxyConfig

class ProxyRotator:
    def __init__(self, proxy_list: Optional[List[Dict]] = None):
        self.proxies: List[ProxyConfig] = []
        self.current_index = 0
        self.lock = threading.Lock()
        if proxy_list:
            for p in proxy_list:
                self.ADD_PROXY(
                    p.get('host', ''), p.get('port', 8080),
                    p.get('protocol', 'http'),
                    p.get('username'), p.get('password')
                )

    def ADD_PROXY(self, host: str, port: int, protocol: str = 'http',
                  username: Optional[str] = None, password: Optional[str] = None):
        with self.lock:
            self.proxies.append(ProxyConfig(
                host=host, port=port, protocol=protocol,
                username=username, password=password
            ))

    def REMOVE_PROXY(self, host: str, port: int):
        with self.lock:
            self.proxies = [p for p in self.proxies if not (p.host == host and p.port == port)]

    def GET_PROXY(self) -> Optional[Dict]:
        if not self.proxies:
            return None
        with self.lock:
            self.proxies.sort(key=lambda p: p.success_count - p.fail_count, reverse=True)
            proxy = self.proxies[self.current_index % len(self.proxies)]
            self.current_index += 1
            proxy.last_used = time.time()
            proxy_url = f"{proxy.protocol}://"
            if proxy.username and proxy.password:
                proxy_url += f"{proxy.username}:{proxy.password}@"
            proxy_url += f"{proxy.host}:{proxy.port}"
            return {'http': proxy_url, 'https': proxy_url, 'config': proxy}