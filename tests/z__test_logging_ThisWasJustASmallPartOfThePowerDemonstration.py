import os
import logging
import time
from jwebs import JWebs

def demonstrate_logging():
    print("=" * 60)
    print("JWEBS LOGGING SYSTEM DEMONSTRATION")
    print("=" * 60)
    
    print("\n[1] Initializing JWebs with logging enabled...")
    
    j = JWebs(
        redirects=True,
        enable_logging=True,
        log_dir="logs",
        log_level=logging.DEBUG,
        log_console=True,
        use_retry=True,
        timeout=10,
        connect_timeout=5
    )
    
    print("✓ Logging system initialized")
    print(f"  Log directory: {os.path.abspath('logs')}")
    
    print("\n[2] Generating requests to create log entries...")
    
    print("  → Sending successful requests...")
    resp1 = j.GET("https://example.com")
    resp2 = j.GET("https://example.com")
    
    print("  → Sending request with redirect...")
    resp3 = j.GET("http://example.com")
    
    print("  → Sending failed request...")
    resp4 = j.GET("https://example.com/notfound", raise_on_error=False)
    
    print("\n[3] Running security audit...")
    security_report = j.SECURITY_AUDIT("https://example.com")
    print(f"  Security grade: {security_report.grade}")
    
    print("\n[4] Running SEO audit...")
    seo_score = j.SEO_AUDIT("https://example.com")
    print(f"  SEO score: {seo_score.overall}")
    
    print("\n[5] Performance test...")
    perf = j.PERFORMANCE_TEST("https://example.com", runs=2)
    print(f"  Load time: {perf.load_time:.3f} seconds")
    
    print("\n[6] Running crawler...")
    crawl_result = j.CRAWL("https://example.com", max_depth=1, max_pages=3)
    print(f"  Crawled {len(crawl_result)} pages")
    
    print("\n[7] Log files generated:")
    log_dir = "logs"
    if os.path.exists(log_dir):
        log_files = os.listdir(log_dir)
        for log_file in sorted(log_files):
            file_path = os.path.join(log_dir, log_file)
            file_size = os.path.getsize(file_path)
            print(f"  • {log_file} ({file_size} bytes)")
    
    print("\n[8] Reading log content (last 3 lines of FastHTTP.log):")
    fasthttp_log = os.path.join(log_dir, "FastHTTP.log")
    if os.path.exists(fasthttp_log):
        with open(fasthttp_log, 'r') as f:
            lines = f.readlines()
            for line in lines[-3:]:
                print(f"    {line.strip()}")
    
    print("\n[9] Disabling logging...")
    j.DISABLE_LOGGING()
    print("  Logging disabled")
    j.GET("https://example.com")
    print("  Request made but no log entry created")
    
    print("\n[10] Re-enabling logging...")
    j.ENABLE_LOGGING(log_dir="logs_new", level=logging.WARNING)
    print("  Logging re-enabled with WARNING level")
    j.GET("https://example.com/notfound", raise_on_error=False)
    print("  Only error-level logs captured")
    
    print("\n[11] Closing connections...")
    j.CLOSE()
    
    print("\n" + "=" * 60)
    print("THIS WAS JUST A SMALL PART OF THE POWER DEMONSTRATION!")
    print("=" * 60)
    print("\n📁 Log files location:", os.path.abspath("logs"))
    print("📁 New log files location:", os.path.abspath("logs_new"))

if __name__ == "__main__":
    demonstrate_logging()