from jwebs import JWebs

def main():
    j = JWebs()
    start_url = "https://example.com"
    result = j.CRAWL(start_url, max_depth=1, max_pages=5, same_domain=True)
    for url, data in result.items():
        print(f"Crawled: {url} - depth {data.get('depth')} - status {data.get('status')}")

if __name__ == "__main__":
    main()