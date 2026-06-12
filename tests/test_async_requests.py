from jwebs import JWebs

def main():
    j = JWebs()
    client = j.async_client
    urls = [
        "https://example.com",
        "https://example.com",
        "https://example.com"
    ]
    responses = client.BATCH_GET(urls)
    for url, resp in responses.items():
        print(f"{url} -> status {resp.status}, {len(resp.body)} bytes")

if __name__ == "__main__":
    main()