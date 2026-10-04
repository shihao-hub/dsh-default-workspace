"""决定性实验：区分「Douyin 侧行为变化」与「我的改动引入了回归」。

用旧方法（纯 Page.navigate，不 Enable Network）导航，等待后检查 performance
里有没有 douyinvod 条目。若同样为空 → 与我的改动无关。
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter

PROJECT = r"D:\Users\language_projects\python_projects\douyin_downloader"
sys.path.insert(0, PROJECT)

import douyin_dl as dl  # noqa: E402

VIDEO = "https://www.douyin.com/video/7691653099139632424"

JS = """(() => {
  const res = performance.getEntriesByType('resource');
  const hosts = {};
  for (const r of res) {
    try { const h = new URL(r.name).host; hosts[h] = (hosts[h] || 0) + 1; } catch (e) {}
  }
  const vids = Array.from(document.querySelectorAll('video'))
    .map(v => ({ src: (v.currentSrc || v.src || '').slice(0, 60), t: v.currentTime || 0, ready: v.readyState }));
  return {
    totalResources: res.length,
    douyinvod: res.filter(r => r.name.includes('douyinvod')).length,
    topHosts: Object.entries(hosts).sort((a, b) => b[1] - a[1]).slice(0, 10),
    videos: vids,
    bufferLimitExceeded: res.length >= 250,
  };
})()"""


def main() -> int:
    ws_url = dl.open_tab(VIDEO, 9222, "douyin.com", navigate=False)

    # 旧方法：纯导航，不 Enable Network
    print("[*] 用旧方法导航（Page.navigate，无 Network.enable）...")
    dl.navigate_page(ws_url, VIDEO)

    prev = 0
    for mark in (5, 10, 20, 30):
        time.sleep(mark - prev)
        prev = mark
        state = dl.eval_cdp(ws_url, JS)
        print(f"  t={mark:>2}s  total={state['totalResources']:>4}  douyinvod={state['douyinvod']:>2}  "
              f"bufferFull={state['bufferLimitExceeded']}  video={state['videos'][:1]}")
        if state["douyinvod"]:
            print("  topHosts:", json.dumps(state["topHosts"], ensure_ascii=False))
            print("\nRESULT: 旧方法能拿到 douyinvod 条目 → 我的改动引入了回归")
            return 0

    final = dl.eval_cdp(ws_url, JS)
    print("\n  topHosts:", json.dumps(final["topHosts"], ensure_ascii=False))
    print("  videos:", json.dumps(final["videos"], ensure_ascii=False))
    print("\nRESULT: 旧方法同样拿不到 douyinvod 条目 → 与我的改动无关，是 Douyin 侧行为")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
