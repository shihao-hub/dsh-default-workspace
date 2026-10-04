"""Minimal Chrome DevTools Protocol driver (no external deps beyond websocket-client).

Usage: python cdp_fetch.py <url> <out.json> [wait_seconds] [js_file]
Navigates a new tab in the resident automation Chrome (port 9222) and dumps
title / location / innerText / anchors to a JSON file (UTF-8).
"""
import json
import sys
import time
import urllib.request

import websocket

DEBUG = "http://127.0.0.1:9222"

DEFAULT_JS = r"""
(() => {
  const out = {url: location.href, title: document.title, text: "", anchors: [], html_len: 0};
  out.text = (document.body ? document.body.innerText : "").slice(0, 6000);
  out.html_len = document.documentElement ? document.documentElement.outerHTML.length : 0;
  const seen = new Set();
  for (const a of document.querySelectorAll("a[href]")) {
    const h = a.href;
    if (h && !seen.has(h)) { seen.add(h); out.anchors.push([h, (a.innerText || "").replace(/\s+/g, " ").slice(0, 120)]); }
    if (out.anchors.length > 400) break;
  }
  return JSON.stringify(out);
})()
"""


def http_json(path):
    with urllib.request.urlopen(DEBUG + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


class CDP:
    def __init__(self):
        v = http_json("/json/version")
        self.ws = websocket.create_connection(
            v["webSocketDebuggerUrl"], timeout=60, max_size=200 * 1024 * 1024
        )
        self._id = 0

    def send(self, method, params=None, session=None):
        self._id += 1
        msg = {"id": self._id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        deadline = time.time() + 60
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
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 6.0
    js = DEFAULT_JS
    if len(sys.argv) > 4:
        with open(sys.argv[4], "r", encoding="utf-8") as f:
            js = f.read()

    cdp = CDP()
    result = {"ok": False}
    try:
        t = cdp.send("Target.createTarget", {"url": "about:blank"})
        tid = t["targetId"]
        sess = cdp.send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        cdp.send("Page.enable", {}, sess)
        cdp.send("Runtime.enable", {}, sess)
        cdp.send("Emulation.setUserAgentOverride",
                 {"userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"}, sess)
        cdp.send("Page.navigate", {"url": url}, sess)
        time.sleep(wait)
        ev = cdp.send("Runtime.evaluate",
                      {"expression": js, "returnByValue": True, "awaitPromise": True}, sess)
        val = ev.get("result", {}).get("value")
        result = {"ok": True, "targetId": tid, "raw": val}
        if isinstance(val, str):
            try:
                result["data"] = json.loads(val)
            except Exception:
                result["data_text"] = val
        else:
            result["data"] = val
        # keep the tab open only if requested; default close it
        cdp.send("Target.closeTarget", {"targetId": tid})
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        cdp.close()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print("wrote", out_path, "ok=", result.get("ok"))


if __name__ == "__main__":
    main()
