"""探针：dump CDP 在导航抖音视频页时返回的 requestWillBeSentExtraInfo 原始结构，
确认 Cookie 到底以什么形式出现（headers 里的 Cookie 字段，还是 associatedCookies）。"""

from __future__ import annotations

import json
import sys
import time

PROJECT = r"D:\Users\language_projects\python_projects\douyin_downloader"
sys.path.insert(0, PROJECT)

import websocket  # noqa: E402
import douyin_dl as dl  # noqa: E402

VIDEO = "https://www.douyin.com/video/7691653099139632424"
PORT = 9222


def main() -> int:
    ws_url = dl.open_tab(VIDEO, PORT, "douyin.com", navigate=False)
    ws = websocket.create_connection(ws_url, timeout=30)
    url_by_request: dict[str, str] = {}
    samples: list[dict] = []
    try:
        ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        ws.send(json.dumps({"id": 101, "method": "Page.navigate", "params": {"url": VIDEO}}))
        ws.settimeout(1.0)
        deadline = time.time() + 12
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
            method = msg.get("method")
            params = msg.get("params") or {}
            if method == "Network.requestWillBeSent":
                rid = params.get("requestId")
                url = (params.get("request") or {}).get("url") or ""
                if rid:
                    url_by_request[rid] = url
            elif method == "Network.requestWillBeSentExtraInfo":
                url = url_by_request.get(params.get("requestId") or "") or ""
                if ".douyinvod.com" in url or "douyin.com" in url:
                    samples.append(
                        {
                            "url": url[:110],
                            "param_keys": sorted(params.keys()),
                            "header_names": sorted((params.get("headers") or {}).keys()),
                            "associated_cookies": [
                                {
                                    "name": c.get("cookie", {}).get("name"),
                                    "domain": c.get("cookie", {}).get("domain"),
                                    "blocked": c.get("blockedReasons"),
                                }
                                for c in (params.get("associatedCookies") or [])
                            ],
                        }
                    )
    finally:
        ws.close()

    print(json.dumps(samples[:6], ensure_ascii=False, indent=2))
    print(f"\ntotal samples: {len(samples)}")
    with_cookie_header = [s for s in samples if any(h.lower() == "cookie" for h in s["header_names"])]
    with_assoc = [s for s in samples if s["associated_cookies"]]
    print(f"samples with Cookie header : {len(with_cookie_header)}")
    print(f"samples with associatedCookies: {len(with_assoc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
