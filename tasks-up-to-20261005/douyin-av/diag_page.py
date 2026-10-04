"""诊断：当前抖音标签页到底是什么状态——正常播放器？验证页？还是纯空白？"""

from __future__ import annotations

import json
import sys

PROJECT = r"D:\Users\language_projects\python_projects\douyin_downloader"
sys.path.insert(0, PROJECT)

import douyin_dl as dl  # noqa: E402

JS = """(() => {
  const vids = Array.from(document.querySelectorAll('video')).map(v => ({
    src: (v.currentSrc || v.src || '').slice(0, 80), ready: v.readyState, dur: v.duration || 0
  }));
  const res = performance.getEntriesByType('resource')
    .map(r => r.name).filter(n => n.includes('douyinvod.com'));
  const body = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').slice(0, 300);
  return {
    title: document.title,
    url: location.href,
    videoCount: vids.length,
    videos: vids,
    douyinvodCount: res.length,
    hasMediaAudio: res.filter(n => n.includes('media-audio')).length,
    hasMediaVideo: res.filter(n => n.includes('media-video')).length,
    bodySample: body,
    htmlLen: document.documentElement.outerHTML.length,
  };
})()"""


def main() -> int:
    tabs = [t for t in dl.get_targets(9222) if t.get("type") == "page"]
    out = []
    for tab in tabs:
        entry = {"tabUrl": tab.get("url", "")[:100]}
        if "douyin.com" in tab.get("url", ""):
            try:
                entry["probe"] = dl.eval_cdp(tab["webSocketDebuggerUrl"], JS)
            except Exception as exc:
                entry["probeError"] = f"{type(exc).__name__}: {exc}"
        out.append(entry)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
