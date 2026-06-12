# jwebs

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PyPI version](https://badge.fury.io/py/jwebs.svg)](https://badge.fury.io/py/jwebs)

<br>

<img src="docs/images/jwebs-logo.png" alt="jwebs logo">

<br>

**jwebs** is a complete, high‑performance library for web scraping, crawling automation, and content analysis. It supports both HTTP/1.1 and HTTP/2 (user selectable) and includes built‑in caching, rate limiting, robots.txt handling, dynamic proxy rotation, distributed crawling (via Redis), data extraction, content differencing, uptime monitoring, Sitemap/RSS generation, and optional AI‑powered extraction.

---

## Quick Start – Simple GET Request

```python
from jwebs import JWebs

j = JWebs()
resp = j.GET("https://example.com")
print(f"Status: {resp.status}")
print(f"Content length: {len(resp.text)}")
```

---

## Main Capabilities

**· HTTP** – HTTP/1.1 and HTTP/2 (user selectable), Keep‑Alive, automatic redirects, batch concurrent requests.

**· Request** Management – Two‑layer cache (memory + SQLite), rate limiting (Token Bucket), robots.txt respect, session management.

**· Security & Flexibility** – User‑Agent rotation, dynamic proxy rotation, client certificates (mTLS), SSL and security headers checking.

**· Crawling & Automation** – Simple crawler and distributed crawler (Redis) that can run across multiple machines.

**· Data Extraction** – Extract text, links, emails, phone numbers, prices, JSON‑LD, meta tags, images, social media links.
· Content Analysis – Sentiment analysis, automatic translation, content differencing (diff).

**· Monitoring** – Uptime monitoring, performance testing (TTFB, page size), SEO and security audits.

**· Utilities** – Sitemap.xml generator, RSS feed generator, GraphQL client, async client.

**· AI** (optional) – Intelligent data extraction via natural language instructions (DeepSeek/OpenAI) and text summarization.

---

## Installation

```bash
# Basic installation (core dependencies only)
pip install jwebs

# With HTTP/2 support
pip install jwebs[http2]

# With distributed crawler (Redis)
pip install jwebs[distributed]

# All optional features
pip install jwebs[all]
```
## Debug

If you don't have Redis, install it using your package manager:

· Ubuntu/Debian: sudo apt install redis
· Termux (Android): pkg install redis
· macOS: brew install redis

Or download from redis.io

---

## More Examples

## HTTP/2 and Caching

```python
from jwebs import JWebs

j = JWebs(http_version='2', use_cache=True)
title = j.GET_TITLE("https://http2.golang.org/")
print(f"Title: {title}")
```

Extracting Emails and Links

```python
from jwebs import JWebs

j = JWebs()
emails = j.EXTRACT_EMAILS("https://example.com")
links = j.GET_LINKS("https://example.com", internal=True)
print(f"Emails: {emails}\nInternal Links: {len(links)}")
```

## Distributed Crawling with Redis

```python
from jwebs import JWebs

j = JWebs()
crawler = j.create_distributed_crawler(redis_url="redis://localhost:6379/0")
crawler.add_seed("https://example.com", depth=0)
crawler.crawl_worker(max_pages=10, max_depth=2, strict_page_limit=True)

results = crawler.get_all_results()
for url, info in results.items():
    print(f"{url} → {info.get('title', 'no title')}")
```

## Security Audit

```python
from jwebs import JWebs

j = JWebs()
report = j.SECURITY_AUDIT("https://example.com")
print(f"SSL valid: {report.ssl_valid}")
print(f"Security grade: {report.grade}")
```

## Content Differencing

```python
from jwebs import JWebs

j = JWebs()
snap1 = j.TAKE_SNAPSHOT("version1", "Hello world")
snap2 = j.TAKE_SNAPSHOT("version2", "Hello jwebs")
diff = j.COMPARE_SNAPSHOTS(snap1, snap2)
print(f"Similarity: {j.SIMILARITY('Hello world', 'Hello jwebs')}")
```

## Uptime Monitor

```python
from jwebs import JWebs
import time

j = JWebs()
j.MONITOR_URL("https://example.com", expected_status=200)
j.START_MONITORING()
time.sleep(5)
j.STOP_MONITORING()
```

---

## Issues and Contributions

You can report bugs via GitHub Issues or submit fixes via pull requests.

---

## Links

**· GitHub repository:**
https://github.com/JCode-JCode/jwebs
**· PyPI page:**
https://pypi.org/project/jwebs/

---

## License

This project is licensed under the Apache License 2.0 – see the LICENSE file for details.

---

Designed and built with love by **J Code**

