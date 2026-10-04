"""核对：我没读过的那 29 张，是否可能藏着"读过的帧里看不到"的新内容。
做法：对每张未读帧，找时间上夹住它的、我已读过的前后两帧，
用与去重相同的指纹（64x36 梯度图）比差异；若它和前后两帧都差得远，
说明它可能是一页我没看到的新画面 -> 标记出来。
"""
import os
import numpy as np
from PIL import Image

D = r"C:\Users\29580\Documents\deepseek-harness\default-workspace\frames\all"
kept = {}
with open(r"C:\Users\29580\Documents\deepseek-harness\default-workspace\frames\kept.txt") as fh:
    for line in fh:
        sec, name = line.strip().split("\t")
        kept[int(sec)] = name

read = ["f_0001","f_0006","f_0013","f_0018","f_0023","f_0033","f_0034","f_0039","f_0041",
        "f_0045","f_0048","f_0051","f_0053","f_0054","f_0060","f_0062","f_0064","f_0066",
        "f_0069","f_0072","f_0080","f_0089","f_0098","f_0100","f_0106","f_0110","f_0115",
        "f_0117","f_0120","f_0122","f_0126","f_0127","f_0130","f_0134","f_0136","f_0140",
        "f_0143","f_0146"]
read_sec = sorted(int(n.replace("f_", "").replace(".jpg", "")) for n in read)
all_sec = sorted(int(f.replace("f_", "").replace(".jpg", "")) for f in os.listdir(D))

def sig(sec):
    im = Image.open(os.path.join(D, "f_%04d.jpg" % sec)).convert("L").resize((64, 36))
    a = np.asarray(im, dtype=np.float32) / 255.0
    gy, gx = np.gradient(a)
    return np.sqrt(gx**2 + gy**2)

cache = {}
def s(sec):
    if sec not in cache:
        cache[sec] = sig(sec)
    return cache[sec]

unread = [sec for sec in all_sec if sec not in read_sec]
lines = [f"总帧 {len(all_sec)} / 已读 {len(read_sec)} / 未读 {len(unread)}", ""]
header = f"{'秒':>5} {'左已读':>8} {'右已读':>8} {'与左差':>9} {'与右差':>9}   判定"
lines.append(header)
flags = []
for sec in unread:
    left = max([r for r in read_sec if r < sec], default=None)
    right = min([r for r in read_sec if r > sec], default=None)
    dl = float(np.abs(s(sec) - s(left)).mean()) if left is not None else None
    dr = float(np.abs(s(sec) - s(right)).mean()) if right is not None else None
    both = min([d for d in (dl, dr) if d is not None])
    tag = ""
    if both > 0.02:
        tag = "  <== 与两侧都差得远，可能含新画面"
        flags.append(sec)
    lines.append(f"{sec:>5} {str(left):>8} {str(right):>8} "
                 f"{('%.4f' % dl) if dl is not None else '-':>9} "
                 f"{('%.4f' % dr) if dr is not None else '-':>9}{tag}")
lines.append("")
lines.append(f"可疑帧数：{len(flags)} -> {['f_%04d.jpg' % s_ for s_ in flags]}")

out = r"C:\Users\29580\Documents\deepseek-harness\default-workspace\frames\verify-report.txt"
with open(out, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines))
print(out)
