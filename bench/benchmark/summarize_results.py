import glob
import re

files = sorted(glob.glob("bench/results/**/*.txt", recursive=True))

patterns = {
    "http_avg": re.compile(r"http_req_duration.*avg=([0-9.]+(?:ms|s))"),
    "http_p95": re.compile(r"p\(95\)=([0-9.]+(?:ms|s))"),
    "http_failed": re.compile(r"http_req_failed.*?([0-9.]+%)"),
    "http_reqs": re.compile(r"http_reqs.*?:\s+([0-9.]+)"),
    "iterations": re.compile(r"iterations.*?:\s+([0-9.]+)"),
    "avg_total_time": re.compile(r"AVG_TOTAL_TIME=([0-9.]+s)"),
    "max_total_time": re.compile(r"MAX_TOTAL_TIME=([0-9.]+s)"),
    "finished": re.compile(r"FINISHED=([0-9]+)"),
    "failed_or_timeout": re.compile(r"FAILED_OR_TIMEOUT=([0-9]+)"),
    "wall_clock": re.compile(r"WALL_CLOCK_S=([0-9.]+)"),
}

for path in files:
    print(f"\n=== {path} ===")
    txt = open(path, encoding="utf-8", errors="ignore").read()
    found = False
    for key, pat in patterns.items():
        m = pat.search(txt)
        if m:
            print(f"{key}: {m.group(1)}")
            found = True
    if not found:
        print("No recognized summary fields found.")