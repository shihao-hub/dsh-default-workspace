# /// script
# requires-python = ">=3.12"
# ///
"""按 streams.json 里的直链下载音频流（带抖音 Referer，否则 CDN 403）。"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

streams_file = sys.argv[1] if len(sys.argv) > 1 else "streams.json"
out_path = sys.argv[2] if len(sys.argv) > 2 else "douyin-333.audio.m4s"

with open(streams_file, encoding="utf-8") as fh:
    data = json.load(fh)

urls = data.get("audio") or []
if not urls:
    raise SystemExit("streams.json 里没有 audio 流")
url = urls[0]

req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
written = 0
with urllib.request.urlopen(req, timeout=60) as resp, open(out_path, "wb") as fh:
    while True:
        chunk = resp.read(1 << 20)
        if not chunk:
            break
        fh.write(chunk)
        written += len(chunk)
        print(f"\r{written / 1024:.0f} KB", end="", file=sys.stderr, flush=True)
print(file=sys.stderr)
print(f"{out_path}\t{written}\t{os.path.getsize(out_path)}", file=sys.stderr)
