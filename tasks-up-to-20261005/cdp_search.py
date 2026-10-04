"""Douyin search via the resident automation Chrome (CDP), with warm-up + header emulation.

Usage: python cdp_search.py <full_search_url> <out.json>
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
    text: (document.body ? document.body.innerText : "").slice(0, 5000),
    anchors: [],
    aweme_ids: [],
    html_len: document.documentElement ? document.documentElement.outerHTML.length : 0
  };
  const html = document.documentElement ? document.documentElement.outerHTML : "";
  const ids = new Set();
  for (const m of html.matchAll(/"(?:aweme_id|awemeId|group_id|groupId)"\s*:\s*"(\d{15,25})"/g)) ids.add(m[1]);
  for (const m of html.matchAll(/modal_id=(\d{15,25})/g)) ids.add(m[1]);
  for (const m of html.matchAll(/\/video\/(\d{15,25})/g)) ids.add(m[1]);
  out.aweme_ids = [...ids].slice(0, 60);
  const seen = new Set();
  for (const a of document.querySelectorAll("a[href]")) {
    const h = a.href;
    if (h && !seen.has(h)) { seen.add(h); out.anchors.push([h, (a.innerText || "").replace(/\s+/g, " ").slice(0, 100)]); }
    if (out.anchors.length > 300) break;
  }
  return JSON.stringify(out);
})()
"""


def http_json(path):
    with urllib.request.urlopen(DEBUG + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


class CDP:
    def __init__(self, ua):
        v = http_json("/json/version")
        self.ws = websocket.create_connection(
            v["webSocketDebuggerUrl"], timeout=90, max_size=200 * 1024 * 1024
        )
        self.ua = ua
        self._id = 0

    def send(self, method, params=None, session=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        deadline = time.time() + 90
        while time.time() < deadline:
            data = json.loads(self.ws.recv())
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(f"{method} -> {data['error']}")
                return data.get("result", {})
        raise TimeoutError(method)

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main():
    url = sys.argv[1]
    out_path = sys.argv[2]
    warm = sys.argv[3] if len(sys.argv) > 3 else "https://www.douyin.com/"

    result = {"ok": False}
    cdp = None
    try:
        cdp = CDP(None)
        ver = http_json("/json/version")
        m = re.search(r"Chrome/([\d.]+)", ver.get("Browser", ""))
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
        steps = []
        if warm:
            cdp.send("Page.navigate", {"url": warm}, sess)
            time.sleep(6)
            ev = cdp.send("Runtime.evaluate",
                          {"expression": "document.title + ' | ' + location.href",
                           "returnByValue": True}, sess)
            steps.append({"warm": ev.get("result", {}).get("value")})
        cdp.send("Page.navigate", {"url": url}, sess)
        time.sleep(9)
        ev = cdp.send("Runtime.evaluate",
                      {"expression": EXTRACT_JS, "returnByValue": True, "awaitPromise": True}, sess)
        val = ev.get("result", {}).get("value")
        result = {"ok": True, "targetId": tid, "ua": ua, "steps": steps}
        try:
            result["data"] = json.loads(val)
        except Exception:
            result["data_text"] = val
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
