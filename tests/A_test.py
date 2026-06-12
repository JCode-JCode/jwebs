# A test of the jwebs library

import time
import sys
from jwebs import JWebs
from jwebs.crawl import DistributedCrawler

# --------
# JWebs Parameters – explained for user reference
# --------

# When creating a JWebs instance, you can customize its behaviour using the
# following parameters (all are optional):
#
# General HTTP:
#   master_timeout (float)      – overrides all other timeouts
#   timeouts (float/tuple)      – (connect, read) timeout in seconds
#   timeout (float)             – read timeout
#   connect_timeout (float)     – connection timeout
#   num_pools (int)             – number of PoolManagers (default 20)
#   pool_maxsize (int)          – max connections per pool (default 50)
#   max_workers (int)           – concurrent workers for BATCH (default 10)
#   rate_limit (float)          – requests per second (0 = unlimited)
#   rate_limit_timeout (float)  – max wait for rate limit token (default 30.0)
#   default_headers (dict)      – custom default headers
#   use_random_ua (bool)        – rotate User-Agent (default False)
#   ua_list (list[str])         – custom User-Agent list
#   referrer (str)              – default Referer header
#   verify_ssl (bool)           – verify SSL certificates (default True)
#   use_retry (bool)            – enable automatic retries (default False)
#   retry_total (int)           – number of retry attempts (default 3)
#   retry_backoff (float)       – exponential backoff factor (default 0.1)
#   retry_status_forcelist (list) – status codes that trigger retry
#   redirects (bool/int)        – follow redirects (default False)
#
# Cache:
#   use_cache (bool)            – enable response caching (default False)
#   cache_ttl (float)           – cache TTL in seconds (default 300.0)
#   cache_max_item_size (int)   – max size per cached item in bytes,
#                                 None = unlimited (default 5*1024*1024)
#
# Logging:
#   enable_logging (bool)       – enable file/console logging (default False)
#   log_dir (str)               – directory for log files (default 'logs')
#   log_level (int)             – logging level (default logging.INFO)
#   log_console (bool)          – print logs to console (default True)
#
# Robots.txt:
#   respect_robots_txt (bool)   – obey robots.txt (default False)
#   robots_user_agent (str)     – user agent for robots.txt (default 'JWebs/2.0')
#   robots_timeout (float)      – timeout for fetching robots.txt (default 5.0)
#
# Sessions:
#   session_idle_timeout (float) – idle session cleanup timeout (default 3600.0)
#   allow_expired_sessions (bool) – use expired sessions (only for FastHTTP)
#
# Security:
#   suppress_ssl_warnings (bool) – hide SSL warnings (default True)
#   client_cert (str)           – path to client certificate (mTLS)
#   client_key (str)            – path to client private key
#   client_cert_password (str)  – password for the private key
#   ca_bundle (str)             – custom CA bundle file
#
# Proxy:
#   use_proxy (bool)            – enable proxy support (default False)
#
# HTTP/2:
#   http_version (str)          – 'auto' (HTTP/1.1), '1.1', or '2' (default 'auto')
#   max_connections (int)       – max concurrent connections for HTTP/2 client
#                                 (default = max_workers * 2)
#
# Group configurations (advanced, take precedence over older parameters):
#   http (dict/HTTPConfig)      – general HTTP settings
#   ai (dict/AIConfig)          – AI engine settings
#   checker (dict/CheckerConfig) – timeouts for Checker module
#   captcha (dict/CaptchaConfig) – captcha solver settings
#   crawler (dict/CrawlerConfig) – simple crawler settings
#   robots (dict/RobotsConfig)  – robots.txt settings
#   logging (dict/LoggingConfig) – logging settings
#   rate_limit_cfg (dict/RateLimitConfig) – rate limit settings
#   async_cfg (dict/AsyncConfig) – AsyncClient settings
#   monitor (dict/MonitorConfig) – uptime monitor settings
#   proxy (dict/ProxyConfigGroup) – proxy on/off
#   client_cert_cfg (dict/ClientCertConfig) – mTLS settings
#
# Old-style parameters (still work but group versions are preferred):
#   checker_ssl_timeout, checker_dns_timeout, checker_port_timeout,
#   checker_ping_timeout, checker_status_timeout, checker_redirect_timeout
#   use_ai, ai_provider, ai_model, ai_api_key, ai_connect_timeout,
#   ai_read_timeout, ai_total_timeout, ai_max_cache_entries,
#   ai_cache_ttl_enabled, ai_cache_ttl_seconds
#   captcha_connect_timeout, captcha_read_timeout, captcha_solve_timeout
#   crawler_request_timeout, crawler_delay
#   monitor_check_timeout, monitor_interval
#   async_timeout, async_connect_timeout
# --------
# Writing a small section with the command for you
# --------

def print_section(title):
    print("\n" + "="*60)
    print(f">>> {title}")
    print("="*60)

def main():
    # Create JWebs instance with desired settings
    j = JWebs(
        enable_logging=True,
        log_console=True,
        use_cache=True,
        cache_ttl=60,
        rate_limit=5,                 # 5 requests per second
        #respect_robots_txt=False,     # default is False, I wrote a decoration
        timeout=10,
        connect_timeout=5,
        use_random_ua=True
    )
    print("✅ JWebs instance created.\n")

    # --------
    # 1. Basic HTTP requests (GET, POST, HEAD, STATUS)
    # --------
    print_section("1. Basic HTTP requests")
    url_base = "https://example.com"

    resp = j.GET(url_base)
    print(f"GET {url_base} -> status={resp.status}, elapsed={resp.elapsed:.2f}s, length={len(resp.text)}")

    resp_head = j.HEAD(url_base)
    print(f"HEAD {url_base} -> status={resp_head.status}")

    code = j.STATUS_CODE(url_base)
    print(f"STATUS_CODE {url_base} -> {code}")

    text = j.TEXT(url_base)
    print(f"TEXT helper -> {len(text)} characters")

    url_json = "https://httpbin.org/json"
    data = j.JSON(url_json)
    print(f"JSON helper -> keys: {list(data.keys()) if data else 'None'}")

    resp_post = j.POST("https://httpbin.org/post", json={"test": "value"})
    print(f"POST -> status={resp_post.status}")

    # 2. Cache test

    print_section("2. Cache test")
    url_cache = "https://httpbin.org/cache/60"
    start = time.time()
    resp1 = j.GET(url_cache)
    t1 = time.time() - start
    start = time.time()
    resp2 = j.GET(url_cache)
    t2 = time.time() - start
    print(f"First request: {t1:.3f}s")
    print(f"Second request (from cache): {t2:.3f}s")
    print(f"Time saved: {(t1 - t2) * 1000:.1f}ms")

    # 3. Rate limit test (5 requests per second)

    print_section("3. Rate limit test (5 requests per second)")
    start = time.time()
    for i in range(6):
        # Use unique URL to bypass cache
        resp = j.GET(f"https://httpbin.org/get?nocache={time.time()}_{i}")
        print(f"  Request {i+1}: status={resp.status}")
    elapsed = time.time() - start
    print(f"Total time for 6 requests: {elapsed:.2f}s (should be >= 1 second)")

    # --------
    # 4. Robots.txt (enabled/disabled)
    # --------
    print_section("4. Robots.txt test")
    j.ENABLE_ROBOTS_RESPECT(user_agent="JWebsTest", timeout=2)
    print(f"robots_enabled: {j.robots_enabled}")
    allowed = j.http.robots_parser.is_allowed("https://example.com") if j.http.robots_parser else True
    print(f"Is allowed to crawl example.com? {allowed}")
    j.DISABLE_ROBOTS_RESPECT()
    print("Robots respect disabled.")

    # --------
    # 5. Checker (SSL, DNS, Security Headers)
    # --------
    print_section("5. Checker (SSL, DNS, Security Headers)")
    url_check = "https://example.com"
    print(f"URL: {url_check}")
    print(f"  IS_HTTPS: {j.IS_HTTPS(url_check)}")
    print(f"  HAS_SSL: {j.HAS_SSL(url_check)}")
    ssl_info = j.GET_SSL_INFO(url_check)
    print(f"  SSL Issuer: {ssl_info.get('issuer', {}).get('organizationName', 'N/A') if ssl_info else 'N/A'}")
    print(f"  IS_UP: {j.IS_UP(url_check)}")
    print(f"  STATUS_CODE: {j.STATUS_CODE(url_check)}")
    dns = j.GET_DNS_INFO(url_check)
    print(f"  DNS IP: {dns.get('ip') if dns else 'N/A'}")
    sec_headers = j.CHECK_SECURITY_HEADERS(url_check)
    print(f"  Security Headers present: {sum(1 for v in sec_headers.values() if v)}/{len(sec_headers)}")
    score, _ = j.GET_SECURITY_SCORE(url_check)
    print(f"  Security Score: {score}/100")

    # --------
    # 6. Builder (Extract)
    # --------
    print_section("6. Builder (Extract)")
    url_extract = "https://example.com"
    title = j.GET_TITLE(url_extract)
    print(f"  Title: {title}")
    links = j.GET_LINKS(url_extract, internal=True, external=False)
    print(f"  Internal Links: {len(links)} found")
    emails = j.EXTRACT_EMAILS(url_extract)
    print(f"  Emails: {emails if emails else 'None'}")
    headings = j.GET_HEADINGS(url_extract)
    print(f"  Headings: H1={len(headings.get('h1',[]))}, H2={len(headings.get('h2',[]))}")
    text_all = j.GET_ALL_TEXT(url_extract, clean=True)
    print(f"  GET_ALL_TEXT length: {len(text_all)}")

    # --------
    # 7. Content Differ
    # --------
    print_section("7. Content Differ")
    text1 = "Python is great for web scraping."
    text2 = "Python is excellent for data extraction."
    similarity = j.SIMILARITY(text1, text2)
    print(f"Similarity between two sentences: {similarity:.2f}")
    snap1 = j.TAKE_SNAPSHOT("snap1", text1)
    snap2 = j.TAKE_SNAPSHOT("snap2", text2)
    diff = j.COMPARE_SNAPSHOTS(snap1, snap2)
    print(f"Snapshot diff: words added={len(diff.get('words_added', []))}, removed={len(diff.get('words_removed', []))}")

    # --------
    # 8. Sitemap & RSS Generator
    # --------
    print_section("8. Sitemap & RSS Generator")
    urls = ["https://example.com", "https://httpbin.org", "https://www.python.org"]
    sitemap_file = j.GENERATE_SITEMAP(urls, "test_sitemap.xml")
    print(f"Sitemap generated: {sitemap_file}")
    rss_items = [{"title": "Example Post", "link": "https://example.com/post", "description": "Just a test"}]
    rss_file = j.GENERATE_RSS(rss_items, "Test Feed", "https://example.com", "Test description", "test_feed.xml")
    print(f"RSS feed generated: {rss_file}")

    # --------
    # 9. Monitor (simple)
    # --------
    print_section("9. Monitor (temporary)")
    url_monitor = "https://example.com"
    monitor_id = j.MONITOR_URL(url_monitor, expected_status=200)
    print(f"Monitor ID: {monitor_id}")
    j.START_MONITORING()
    time.sleep(3)  # allow one check
    j.STOP_MONITORING()
    status_info = j.GET_MONITOR_STATUS()._monitored_urls.get(monitor_id, {})
    print(f"Monitor last status: {status_info.get('last_status', 'N/A')}")

    # --------
    # 10. Distributed Crawler (requires Redis)
    # --------
    print_section("10. Distributed Crawler (Redis)")
    try:
        crawler = DistributedCrawler(redis_url="redis://localhost:6379/0", request_timeout=5)
        crawler.clear()
        crawler.add_seed("https://example.com", depth=0)
        print("  Running worker for max 2 pages...")
        crawler.crawl_worker(max_pages=2, max_depth=1, delay=0.1, strict_page_limit=False)
        results = crawler.get_all_results()
        print(f"  Crawled {len(results)} pages:")
        for url, info in results.items():
            print(f"    - {url} : {info.get('title', 'no title')[:50]}")
        crawler.CLOSE()
    except Exception as e:
        print(f"  Distributed Crawler skipped (Redis not available?): {e}")

    # --------
    # 11. AsyncClient (BATCH_GET)
    # --------
    print_section("11. AsyncClient (BATCH_GET)")
    async_client = j.async_client
    urls_batch = ["https://example.com", "https://httpbin.org/ip", "https://httpbin.org/user-agent"]
    results_batch = async_client.BATCH_GET(urls_batch)
    for url, resp in results_batch.items():
        print(f"  {url.split('/')[2]}: status={resp.status}, time={resp.elapsed:.2f}s")
    async_client.CLOSE()

    # --------
    # 12. History & Stats
    # --------
    print_section("12. History & Stats")
    stats = j.GET_STATS()
    print(f"Total requests: {stats.get('total_requests', 0)}")
    history = j.GET_HISTORY(5)
    print("Last 5 requests:")
    for req in history:
        print(f"  {req.method} {req.url} -> {req.status} ({req.duration:.2f}s)")

    # --------
    # 13. Cleanup
    # --------
    print_section("13. Cleanup")
    j.CLEAR_CACHE()
    j.CLEAR_HISTORY()
    j.CLOSE()
    print("✅ Cache and history cleared. Connections closed.")

if __name__ == "__main__":
    main()