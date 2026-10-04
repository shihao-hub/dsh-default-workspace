"""A 部分验证：构造视频/音频时长不等的场景，确认 merge_av_streams 会裁到重叠区间。

生成 10s 视频 + 5s 音频，合并后输出应≈5s（旧实现会得到 10s，尾部 5s 是冻结帧）。
"""

from __future__ import annotations

import os
import subprocess
import sys

PROJECT = r"D:\Users\language_projects\python_projects\douyin_downloader"
sys.path.insert(0, PROJECT)

import douyin_dl as dl  # noqa: E402

OUT = r"C:\Users\29580\Documents\deepseek-harness\default-workspace\douyin-av\av-trim-test"


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(cmd)}\n{proc.stderr[-800:]}")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    video = os.path.join(OUT, "v10.mp4")
    audio = os.path.join(OUT, "a5.m4a")
    merged = os.path.join(OUT, "merged.mp4")

    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc=size=320x240:rate=15", "-t", "10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", video])
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440", "-t", "5", "-c:a", "aac", audio])

    v_dur = dl.probe_duration(video)
    a_dur = dl.probe_duration(audio)
    print(f"inputs      : video={v_dur:.3f}s audio={a_dur:.3f}s")

    if os.path.exists(merged):
        os.remove(merged)
    ok = dl.merge_av_streams(video, audio, merged)
    out_dur = dl.probe_duration(merged)
    print(f"merge ok    : {ok}")
    print(f"output dur  : {out_dur:.3f}s   (期望≈{min(v_dur, a_dur):.3f}s)")

    # 对齐场景：两条等长，不应被裁
    same = os.path.join(OUT, "same.mp4")
    same_a = os.path.join(OUT, "a10.m4a")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "sine=frequency=440", "-t", "10", "-c:a", "aac", same_a])
    if os.path.exists(same):
        os.remove(same)
    ok2 = dl.merge_av_streams(video, same_a, same)
    same_dur = dl.probe_duration(same)
    print(f"aligned ok  : {ok2}")
    print(f"aligned dur : {same_dur:.3f}s   (期望≈10.000s，不应被裁短)")

    # 头部过滤：覆盖 FetchV 六连、CDP 伪头、Host/Connection、if-range、大小写重复
    recorded = {
        "Referer": "https://www.douyin.com/",
        "referer": "https://www.douyin.com/",
        "Cookie": "ttwid=abc; msToken=xyz",
        "User-Agent": "RealUA/1.0",
        "user-agent": "RealUA/1.0",
        "Range": "bytes=0-",
        "If-Range": '"etag"',
        "Content-Length": "123",
        "Content-Type": "video/mp4",
        "Accept-Encoding": "gzip",
        "Accept": "*/*",
        "Accept-Language": "zh-CN",
        "Host": "v95-web-sz.douyinvod.com",
        "Connection": "keep-alive",
        ":authority": "v95-web-sz.douyinvod.com",
        ":method": "GET",
        "Origin": "https://www.douyin.com",
    }
    kept = dl.replayable_headers(recorded)
    print(f"replay kept : {sorted(kept)}")
    print(f"replay drop : {sorted(set(k.lower() for k in recorded) - set(kept))}")

    expect_kept = {"referer", "cookie", "user-agent", "origin"}
    passed = (
        ok and out_dur <= min(v_dur, a_dur) + 0.35
        and ok2 and abs(same_dur - 10.0) < 0.35
        and set(kept) == expect_kept
    )
    print("RESULT      :", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
