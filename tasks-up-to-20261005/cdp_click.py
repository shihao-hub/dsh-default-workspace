"""Click the target search result on Douyin and report where it navigates.

Usage: python cdp_click.py <search_url> <title_needle> <out.json> [wait_seconds]
"""
import json
import re
import sys
import time
import urllib.request

import websocket

DEBUG = "http://127.0.0.1:9222"

FIND_JS = r"""
(() => {
  const needle = %NEEDLE%;
  const hits = [];
  const walk = (el) => {
    for (const child of el.children) {
      const t = (child.innerText || "");
      if (t.includes(needle)) {
        if (![...child.children].some(c => (c.innerText || "").includes(needle))) {
          hits.push(child);
        } else {
          walk(child);
        }
      }
    }
  };
  walk(document.body);
  const out = {hits: hits.length, cands: []};
  for (const el of hits.slice(0, 6)) {
    const r = el.getBoundingClientRect();
    let node = el, ids = [], attrs = [];
    for (let i = 0; i < 12 && node; i++) {
      for (const a of node.attributes || []) {
        if (/id|data-|href/i.test(a.name)) attrs.push(`${a.name}=${String(a.value).slice(0, 120)}`);
      }
      const propsKey = Object.keys(node).find(k => k.startsWith("__reactProps") || k.startsWith("__reactFiber"));
      if (propsKey) {
        try { ids.push(JSON.stringify(node[propsKey]).match(/\d{17,20}/g) || []); } catch (e) {}
      }
      const href = node.getAttribute && node.getAttribute("href");
      if (href) attrs.push("href=" + href);
      node = node.parentElement;
    }
    out.cands.push({
      text: (el.innerText || "").replace(/\s+/g, " ").slice(0, 200),
      rect: {x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height},
      attrs: attrs.slice(0, 40),
      react_ids: ids.flat().filter((v, i, a) => a.indexOf(v) === i).slice(0, 20)
    });
  }
  out.html_around = [];
  const html = document.documentElement.outerHTML;
  let idx = html.indexOf(needle);
  let guard = 0;
  while (idx >= 0 && guard < 3) {
    out.html_around.push(html.slice(Math.max(0, idx - 1200), idx + 400));
    idx = html.indexOf(needle, idx + 1);
    guard++;
  }
  return JSON.stringify(out);
})()
"""


def http_json(path):
    with urllib.request.urlopen(DEBUG + path, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


class CDP:
    def __init__(self):
        self.ver = http_json("/json/version")
        self.ws = websocket.create_connection(
            self.ver["webSocketDebuggerUrl"], timeout=30, max_size=200 * 1024 * 1024
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
        raise TimeoutError(f"no reply id={want_id}")

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
    needle = sys.argv[2]
    if needle.startswith("@"):
        with open(needle[1:], "r", encoding="utf-8") as f:
            needle = f.read().strip()
    out_path = sys.argv[3]
    wait = float(sys.argv[4]) if len(sys.argv) > 4 else 18.0

    result = {"ok": False}
    cdp = None
    try:
        cdp = CDP()
        m = re.search(r"Chrome/([\d.]+)", cdp.ver.get("Browser", ""))
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              f"(KHTML, like Gecko) Chrome/{m.group(1) if m else '153.0.0.0'} Safari/537.36")
        tid = cdp.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        sess = cdp.send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        for d in ("Page", "Runtime", "Network"):
            cdp.send(f"{d}.enable", {}, sess)
        cdp.send("Emulation.setUserAgentOverride",
                 {"userAgent": ua, "acceptLanguage": "zh-CN,zh;q=0.9", "platform": "Win32"}, sess)

        cdp.send("Page.navigate", {"url": "https://www.douyin.com/jingxuan"}, sess)
        cdp.pump(6)
        cdp.send("Page.bringToFront", {}, sess)
        cdp.send("Page.navigate", {"url": url}, sess)
        cdp.send("Page.bringToFront", {}, sess)
        cdp.pump(wait)

        js = FIND_JS.replace("%NEEDLE%", json.dumps(needle))
        ev = cdp.send("Runtime.evaluate",
                      {"expression": js, "returnByValue": True, "awaitPromise": True}, sess)
        val = ev.get("result", {}).get("value") or "{}"
        info = json.loads(val)
        result = {"ok": True, "targetId": tid, "search_info": info}

        cands = info.get("cands") or []
        clicked = False
        for c in cands:
            r = c.get("rect") or {}
            if not r.get("w") or not r.get("h"):
                continue
            x, y = r["x"], r["y"]
            cdp.send("Input.dispatchMouseEvent",
                     {"type": "mouseMoved", "x": x, "y": y, "button": "none"}, sess)
            cdp.send("Input.dispatchMouseEvent",
                     {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}, sess)
            cdp.send("Input.dispatchMouseEvent",
                     {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}, sess)
            clicked = True
            break
        result["clicked"] = clicked
        cdp.pump(8)
        ev2 = cdp.send("Runtime.evaluate",
                       {"expression": "JSON.stringify({url: location.href, title: document.title, text: (document.body?document.body.innerText:'').slice(0,1500)})",
                        "returnByValue": True}, sess)
        after = ev2.get("result", {}).get("value")
        result["after_click"] = json.loads(after) if after else None
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
