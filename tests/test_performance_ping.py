from jwebs import JWebs

def main():
    j = JWebs()
    url = "https://example.com"

    ping_res = j.PING(url, count=3, timeout=5)
    print(f"Ping avg: {ping_res['avg_time']:.2f} ms, packet loss: {ping_res['packet_loss']}%")

    perf = j.PERFORMANCE_TEST(url, runs=2)
    print(f"Avg load time: {perf.load_time:.2f} sec")
    print(f"Page size: {perf.page_size / 1024:.2f} KB")

if __name__ == "__main__":
    main()