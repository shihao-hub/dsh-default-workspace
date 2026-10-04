# -*- coding: utf-8 -*-
"""把 index.html 渲染成 PNG：Chrome headless 出图 + 用 --dump-dom 量真实内容高度后裁掉多余空白。"""
import pathlib
import re
import subprocess
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HTML = ROOT / "index.html"
RAW = ROOT / "_raw.png"
OUT = ROOT / "wortox-loot.png"
WIDTH = 1240
MAXH = 6000


def run(args, capture=False):
    return subprocess.run(args, capture_output=capture, text=True,
                          encoding="utf-8", errors="replace")


def content_height():
    """渲染一版带测量脚本的副本，读回 .page 的实际高度。"""
    src = HTML.read_text(encoding="utf-8")
    probe = src.replace(
        "</body>",
        '<script>window.addEventListener("load",()=>{document.title="H="+'
        'Math.ceil(document.querySelector(".page").getBoundingClientRect().height+'
        'parseFloat(getComputedStyle(document.querySelector(".page")).paddingTop)*0);});</script></body>')
    p = ROOT / "_measure.html"
    p.write_text(probe, encoding="utf-8")
    r = run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             f"--window-size={WIDTH},{MAXH}", "--virtual-time-budget=1200",
             "--dump-dom", p.as_uri()], capture=True)
    m = re.search(r"<title>H=(\d+)</title>", r.stdout or "")
    if not m:
        m = re.search(r"H=(\d{3,5})", r.stdout or "")
    return int(m.group(1)) if m else None


def main():
    h = content_height()
    print(f"content height: {h}")
    args = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
            "--force-device-scale-factor=2", f"--window-size={WIDTH},{MAXH}",
            "--virtual-time-budget=2500", f"--screenshot={RAW}", HTML.as_uri()]
    r = run(args, capture=True)
    if not RAW.exists():
        print("chrome failed:", (r.stderr or r.stdout or "")[-1500:])
        sys.exit(1)
    im = Image.open(RAW)
    print(f"raw: {im.size[0]}x{im.size[1]}")
    target = h * 2 if h else im.size[1]
    # 从底部往上找最后一行非纯背景，兜底裁切
    if target and target < im.size[1]:
        im = im.crop((0, 0, im.size[0], target))
    im.save(OUT)
    print(f"wrote {OUT.name}: {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
