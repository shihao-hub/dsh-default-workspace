import os, subprocess, sys
import numpy as np
from PIL import Image

SRC = r"C:\Users\29580\Downloads\douyin_7692022955122937098.mp4"
OUT = r"C:\Users\29580\Documents\deepseek-harness\default-workspace\frames\all"
os.makedirs(OUT, exist_ok=True)

# extract 1 fps frames
cmd = ["ffmpeg", "-v", "error", "-y", "-i", SRC, "-vf", "fps=1", os.path.join(OUT, "f_%04d.jpg")]
subprocess.run(cmd, check=True)

files = sorted(os.listdir(OUT))
print("frames:", len(files))

def sig(path):
    im = Image.open(path).convert("L").resize((64, 36))
    a = np.asarray(im, dtype=np.float32) / 255.0
    # edge-ish signature: gradient magnitude
    gy, gx = np.gradient(a)
    return np.sqrt(gx**2 + gy**2)

sigs = [sig(os.path.join(OUT, f)) for f in files]
kept = [0]
for i in range(1, len(sigs)):
    d = float(np.abs(sigs[i] - sigs[kept[-1]]).mean())
    if d > 0.02:
        kept.append(i)
print("distinct:", len(kept))
with open(r"C:\Users\29580\Documents\deepseek-harness\default-workspace\frames\kept.txt", "w") as fh:
    for i in kept:
        fh.write(f"{i+1}\t{files[i]}\n")
print("\n".join(f"{i+1}s {files[i]}" for i in kept))
