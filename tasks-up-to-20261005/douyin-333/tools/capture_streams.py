# /// script
# requires-python = ">=3.12"
# dependencies = ["websocket-client>=1.8"]
# ///
"""复用 douyin_dl 启动的 Chrome（CDP 9222），抓取视频页上全部 douyinvod 流地址。

douyin_dl 自身过滤掉了 media-audio（只要无水印视频画面），本脚本把音频流也捞出来，
补上转写所需的音轨。
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

import websocket

PORT = 9222
VIDEO_URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyin.com/video/7691954855094553856"
OUT_JSON = sys.argv[2] if len(sys.argv) > 2 else "streams.json"


def targets() -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as resp:
        return json.load(resp)


def cdp(ws_url: str, method: str, params: dict | None = None, timeout: float = 20.0):
    ws = websocket.create_connection(ws_url, timeout=timeout)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            res = json.loads(ws.recv())
            if res.get("id") == 1:
                if "error" in res:
                    raise RuntimeError(res["error"])
                return res.get("result", {})
    finally:
        ws.close()


def evaluate(ws_url: str, expression: str):
    res = cdp(ws_url, "Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
    return res.get("result", {}).get("value")


pages = [t for t in targets() if t.get("type") == "page" and "douyin.com" in t.get("url", "")]
if not pages:
    raise SystemExit("没有找到 douyin.com 的 page target（Chrome 是否在 9222 上运行？）")
ws_url = pages[0]["webSocketDebuggerUrl"]
print(f"[*] tab: {pages[0]['url']}", file=sys.stderr)

print(f"[*] navigate -> {VIDEO_URL}", file=sys.stderr)
cdp(ws_url, "Page.navigate", {"url": VIDEO_URL})
time.sleep(3)

names: list[str] = []
for _ in range(20):
    got = evaluate(
        ws_url,
        "performance.getEntriesByType('resource').map(r => r.name)"
        ".filter(n => n.includes('douyinvod.com'))",
    ) or []
    names = list(dict.fromkeys(got))
    if any("media-audio" in n for n in names) and any("media-video" in n for n in names):
        break
    # 兜底：让播放器动起来，触发音频流请求
    evaluate(ws_url, "document.querySelectorAll('video').forEach(v => { v.muted = false; v.play().catch(()=>{}); })")
    time.sleep(1.5)

audio = [n for n in names if "media-audio" in n]
video = [n for n in names if "media-video" in n]
other = [n for n in names if n not in audio and n not in video]

title = evaluate(ws_url, "document.title") or ""
payload = {"video_url": VIDEO_URL, "title": title, "audio": audio, "video": video, "other": other}
with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)

print(f"[+] title: {title}", file=sys.stderr)
print(f"[+] audio streams: {len(audio)}", file=sys.stderr)
print(f"[+] video streams: {len(video)}", file=sys.stderr)
print(f"[+] other douyinvod: {len(other)}", file=sys.stderr)
print(f"[+] saved: {OUT_JSON}", file=sys.stderr)
for n in audio:
    print(f"    AUDIO {n[:120]}", file=sys.stderr)
