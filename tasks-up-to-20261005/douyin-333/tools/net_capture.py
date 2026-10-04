# /// script
# requires-python = ">=3.12"
# dependencies = ["websocket-client>=1.8"]
# ///
"""经 CDP Network 域监听页面真实发出的媒体请求，抓出 media-video / media-audio 流地址。

resource timing 不记录 <video>/媒体请求，所以只能从 Network.requestWillBeSent 事件里捞。
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
SECONDS = float(sys.argv[3]) if len(sys.argv) > 3 else 40.0

with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as resp:
    targets = json.load(resp)
pages = [t for t in targets if t.get("type") == "page" and "douyin.com" in t.get("url", "")]
if not pages:
    raise SystemExit("no douyin page target")
ws_url = pages[0]["webSocketDebuggerUrl"]

ws = websocket.create_connection(ws_url, timeout=5)
ws.settimeout(2.0)


def send(msg_id: int, method: str, params: dict | None = None) -> None:
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))


send(1, "Network.enable", {"maxTotalBufferSize": 100_000_000, "maxResourceBufferSize": 50_000_000})
send(2, "Page.enable")
time.sleep(0.5)
send(3, "Page.navigate", {"url": VIDEO_URL})
print(f"[*] listening network for {SECONDS}s ...", file=sys.stderr)

seen: dict[str, dict] = {}
deadline = time.time() + SECONDS
while time.time() < deadline:
    try:
        raw = ws.recv()
    except websocket.WebSocketTimeoutException:
        continue
    except Exception as exc:  # noqa: BLE001
        print(f"[!] ws closed: {exc}", file=sys.stderr)
        break
    if not raw:
        continue
    try:
        msg = json.loads(raw)
    except ValueError:
        continue
    method = msg.get("method")
    if method != "Network.requestWillBeSent":
        continue
    req = msg["params"]["request"]
    url = req.get("url", "")
    if "douyinvod.com" not in url:
        continue
    key = url.split("?")[0]
    seen.setdefault(key, {"url": url, "type": msg["params"].get("type"), "headers": req.get("headers", {})})
    kind = "audio" if "media-audio" in url else ("video" if "media-video" in url else "unknown")
    print(f"[+] {kind:7s} {msg['params'].get('type'):6s} {url[:110]}", file=sys.stderr)
ws.close()

audio = [v["url"] for v in seen.values() if "media-audio" in v["url"]]
video = [v["url"] for v in seen.values() if "media-video" in v["url"]]
other = [v["url"] for v in seen.values() if v["url"] not in audio and v["url"] not in video]
with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump({"video_url": VIDEO_URL, "audio": audio, "video": video, "other": other}, fh, ensure_ascii=False, indent=2)
print(f"[+] audio={len(audio)} video={len(video)} other={len(other)} -> {OUT_JSON}", file=sys.stderr)
