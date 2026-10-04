"""Douyin search probe: navigates with CDP, captures XHR bodies, extracts aweme ids/titles.

Usage: python cdp_probe.py <search_url> <out.json> [wait_seconds] [warm_url]
"""
import json
import re
import sys
import time
import urllib.request

import websocket

DEBUG = "http://127.0.0.1:9222"

EXTRACT_JS = r"""
(() => {
  const out = {
    url: location.href,
    title: document.title,
    text: (document.body ? document.body.innerText : "").slice(0, 4000),
    anchors: [], aweme_ids: []
  };
  const html = document.documentElement ? document.documentElement.outerHTML : "";
  const ids = new Set();
  for (const m of html.matchAll(/"(?:aweme_id|awemeId|group_id|groupId)"\s*:\s*"(\d{15,25})"/g)) ids.add(m[1]);
  for (const m of html.matchAll(/modal_id=(\d{15,25})/g)) ids.add(m[1]);
  for (const m of html.matchAll(/\/video\/(\d{15,25})/g)) ids.add(m[1]);
  out.aweme_ids = [...ids].slice(0, 80);
  const seen = new Set();
  for (const a of document.querySelectorAll("a[href]")) {
    const h = a.href;
    if (!seen.has(h) && /\/video\/|modal_id=|\/user\//.test(h)) { seen.add(h); out.anchors.push([h, (a.innerText || "").replace(/\s+/g, " ").slice(0, 100)]); }
    if (out.anchors.length > 200) break;
  }
  return JSON.stringify(out);
})()
"""


def http_json(path):
    with urllib.request.urlopen(DEBUG + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


class CDP:
    def __init__(self):
        ver = http_json("/json/version")
        self.ver = ver
        self.ws = websocket.create_connection(
            ver["webSocketDebuggerUrl"], timeout=30, max_size=200 * 1024 * 1024
        )
        self._id = 0
        self._pending = {}
        self.events = []

    def _pump_until(self, want_id, hard_timeout=90):
        end = time.time() + hard_timeout
        while time.time() < end:
            if want_id in self._pending:
                return self._pending.pop(want_id)
            self.ws.settimeout(max(0.1, min(2.0, end - time.time())))
            try:
                data = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if "id" in data:
                self._pending[data["id"]] = data
            else:
                self.events.append(data)
        raise TimeoutError(f"no reply for id={want_id}")

    def send(self, method, params=None, session=None, timeout=90):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        rep = self._pump_until(self._id, timeout)
        if "error" in rep:
            raise RuntimeError(f"{method} -> {rep['error']}")
        return rep.get("result", {})

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.ws.settimeout(max(0.1, min(2.0, end - time.time())))
            try:
                data = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if "id" in data:
                self._pending[data["id"]] = data
            else:
                self.events.append(data)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main():
    url = sys.argv[1]
    out_path = sys.argv[2]
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
    warm = sys.argv[4] if len(sys.argv) > 4 else "https://www.douyin.com/jingxuan"

    result = {"ok": False}
    cdp = None
    try:
        cdp = CDP()
        m = re.search(r"Chrome/([\d.]+)", cdp.ver.get("Browser", ""))
        full_ver = m.group(1) if m else "153.0.0.0"
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              f"(KHTML, like Gecko) Chrome/{full_ver} Safari/537.36")
        tid = cdp.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        sess = cdp.send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        for domain in ("Page", "Runtime", "Network"):
            cdp.send(f"{domain}.enable", {}, sess)
        cdp.send("Network.setExtraHTTPHeaders",
                 {"headers": {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}}, sess)
        cdp.send("Emulation.setUserAgentOverride",
                 {"userAgent": ua, "acceptLanguage": "zh-CN,zh;q=0.9", "platform": "Win32"}, sess)

        cdp.send("Page.navigate", {"url": warm}, sess)
        cdp.pump(6)
        cdp.send("Page.bringToFront", {}, sess)

        mark = len(cdp.events)
        cdp.send("Page.navigate", {"url": url}, sess)
        cdp.send("Page.bringToFront", {}, sess)
        cdp.pump(wait)

        ev = cdp.send("Runtime.evaluate",
                      {"expression": EXTRACT_JS, "returnByValue": True, "awaitPromise": True}, sess)
        val = ev.get("result", {}).get("value")
        result = {"ok": True, "targetId": tid, "ua": ua}
        try:
            result["data"] = json.loads(val)
        except Exception:
            result["data_text"] = val

        # collect interesting network responses captured during/after navigation
        reqs = {}
        for e in cdp.events[mark:]:
            if e.get("method") == "Network.responseReceived":
                p = e["params"]
                reqs[p["requestId"]] = {
                    "url": p["response"]["url"],
                    "status": p["response"]["status"],
                    "mime": p["response"].get("mimeType", ""),
                }
            elif e.get("method") == "Network.loadingFailed":
                p = e["params"]
                reqs.setdefault(p.get("requestId", "?"), {})["failed"] = p.get("errorText")
        interesting = {k: v for k, v in reqs.items()
                       if re.search(r"search|aweme|user/profile|/web/", v.get("url", ""))}
        bodies = {}
        for rid, info in list(interesting.items())[:25]:
            if info.get("status") != 200 or "json" not in (info.get("mime") or ""):
                continue
            try:
                b = cdp.send("Network.getResponseBody", {"requestId": rid}, sess)
                body = b.get("body", "")
                if b.get("base64Encoded"):
                    continue
                bodies[info["url"]] = body[:200000]
            except Exception as ex:
                bodies[info["url"]] = f"<error: {ex}>"
        result["network"] = {
            "response_count": len(reqs),
            "interesting": [{"url": v.get("url"), "status": v.get("status"),
                             "failed": v.get("failed")} for v in list(interesting.values())[:30]],
        }
        # extract ids / titles from captured json bodies
        found = {}
        for u, body in bodies.items():
            for m2 in re.finditer(r'"aweme_id"\s*:\s*"(\d{15,25})"', body):
                found.setdefault(m2.group(1), {"sources": []})["sources"].append(u)
            for m2 in re.finditer(r'"desc"\s*:\s*"([^"]{0,80})"', body):
                found.setdefault(m2.group(1), {"sources": []})["sources"].append(u)
        result["captured"] = {
            "body_urls": list(bodies.keys()),
            "found": {k: v for k, v in list(found.items())[:80]},
        }
        cdp.send("Target.closeTarget", {"targetId": tid})
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        if cdp:
            cdp.close()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("wrote", out_path, "ok=", result.get("ok"), "err=", result.get("error", ""))


if __name__ == "__main__":
    main()
