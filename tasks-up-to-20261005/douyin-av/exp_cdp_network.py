"""关键实验：CDP Network 事件能否看到 Resource Timing 看不到的媒体请求？

Resource Timing 缓冲已满（250 条）且看不到任何媒体 CDN 请求；本实验对比
「页面 target 的 Network 事件」与「Worker target 的 Network 事件」谁能看到。
"""

from __future__ import annotations

import json
import sys
import time

PROJECT = r"D:\Users\language_projects\python_projects\douyin_downloader"
sys.path.insert(0, PROJECT)

import websocket  # noqa: E402
import douyin_dl as dl  # noqa: E402

VIDEO = "https://www.douyin.com/video/7691653099139632424"
MEDIA_HINT = ("douyinvod", "media-video", "media-audio", "/video/tos/")


def main() -> int:
    ws_url = dl.open_tab(VIDEO, 9222, "douyin.com", navigate=False)
    ws = websocket.create_connection(ws_url, timeout=30)
    seen: dict[str, dict] = {}
    sessions = {"page": 0, "worker": 0}
    try:
        ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        ws.send(json.dumps({"id": 2, "method": "Target.setAutoAttach",
                            "params": {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}}))
        ws.send(json.dumps({"id": 101, "method": "Page.navigate", "params": {"url": VIDEO}}))
        ws.settimeout(1.0)
        deadline = time.time() + 28
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                break
            if not raw:
                continue
            msg = json.loads(raw)
            method = msg.get("method") or ""
            params = msg.get("params") or {}
            sid = msg.get("sessionId")
            if method == "Target.attachedToTarget":
                sessions["worker"] += 1
                info = params.get("targetInfo") or {}
                print(f"  [attached] {info.get('type')} {str(info.get('url'))[:70]}")
                new_sid = params.get("sessionId")
                if new_sid:
                    ws.send(json.dumps({"id": 900, "method": "Network.enable", "sessionId": new_sid}))
                continue
            if method == "Network.responseReceived":
                resp = params.get("response") or {}
                url = resp.get("url") or ""
                if any(h in url for h in MEDIA_HINT):
                    key = url.split("?")[0]
                    seen.setdefault(key, {
                        "url": url[:130],
                        "mime": resp.get("mimeType"),
                        "status": resp.get("status"),
                        "fromWorker": bool(sid),
                        "encodedDataLength": resp.get("encodedDataLength"),
                    })
            elif method == "Network.requestWillBeSent":
                url = ((params.get("request") or {}).get("url")) or ""
                if any(h in url for h in MEDIA_HINT):
                    seen.setdefault(url.split("?")[0], {"url": url[:130], "reqOnly": True})
    finally:
        ws.close()

    print(f"\nattached targets: {sessions['worker']}")
    print(f"media-hinted requests seen via CDP: {len(seen)}")
    for item in list(seen.values())[:8]:
        print("  ", json.dumps(item, ensure_ascii=False))

    # 同一时刻 Resource Timing 里有多少
    rt = dl.eval_cdp(ws_url, "performance.getEntriesByType('resource').filter(r=>r.name.includes('douyinvod')).length")
    print(f"\nResource Timing douyinvod count: {rt}")
    print("\n结论:", "CDP 能看到 → 应把嗅探层换成 CDP Network 事件"
          if seen else "CDP 页 target 也看不到 → 需要 Target.setAutoAttach 覆盖 Worker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
