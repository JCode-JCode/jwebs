from jwebs import JWebs

def main():
    j = JWebs()
    url = "https://example.com"

    sec = j.SECURITY_AUDIT(url)
    print(f"SSL valid: {sec.ssl_valid}")
    print(f"Security grade: {sec.grade} (score {sec.score})")
    print(f"Missing headers: {[h for h, v in sec.security_headers.items() if not v]}")

    seo = j.SEO_AUDIT(url)
    print(f"SEO overall score: {seo.overall}")
    print(f"Recommendations: {seo.recommendations[:2]}")

if __name__ == "__main__":
    main()
    
#Besides this feature of checking SSL and even viewing SSL certificate details, there are many other exciting things...