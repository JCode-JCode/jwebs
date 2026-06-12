from jwebs import JWebs

def main():
    j = JWebs(redirects=True)
    url = "https://example.com"

    title = j.GET_TITLE(url)
    print(f"Title: {title}")

    all_text = j.GET_ALL_TEXT(url, clean=True)
    print(f"All text (first 200 chars): {all_text[:200]}...")

    links = j.GET_LINKS(url, unique=True)
    print(f"Total unique links: {len(links)}")
    if links:
        print(f"First link: {links[0]}")

if __name__ == "__main__":
    main()