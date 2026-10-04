# -*- coding: utf-8 -*-
"""Parallel OCR of scanned PostgreSQL book PDF -> utf8 text with page markers."""
import sys, time, multiprocessing as mp
from pathlib import Path

PDF = r"D:\BaiduNetdiskDownload\PostgreSQL数据库内核分析_12908238_彭智勇....pdf"
OUT = Path(r"C:\Users\29580\Documents\deepseek-harness\default-workspace\pgkernel_ocr")
OUT.mkdir(exist_ok=True)

def page_img(reader, pno):
    from PIL import Image
    import numpy as np
    page = reader.pages[pno]
    xo = page["/Resources"]["/XObject"]
    name, ref = list(xo.items())[0]
    o = ref.get_object()
    bpc = o.get("/BitsPerComponent", 8)
    w, h = o["/Width"], o["/Height"]
    if bpc == 4 and o.get("/ColorSpace") == "/DeviceGray":
        data = o.get_data()
        rb = (w * 4 + 7) // 8
        arr = np.frombuffer(data, dtype=np.uint8)[:rb * h].reshape(h, rb)
        px = np.empty((h, rb * 2), dtype=np.uint8)
        px[:, 0::2] = arr >> 4
        px[:, 1::2] = arr & 0x0F
        img = (px[:, :w].astype(np.uint16) * 17).astype(np.uint8)
        return Image.fromarray(img)
    # fallback: generic path
    import io
    im = Image.open(io.BytesIO(page.images[0].data))
    if im.mode == "P":
        im = im.convert("L")
        if im.getextrema() == (0, 15):
            im = im.point(lambda v: v * 17)
    return im

def worker(args):
    lo, hi = args  # 0-based inclusive range
    import pypdf, gc
    from rapidocr_onnxruntime import RapidOCR
    reader = pypdf.PdfReader(PDF)
    ocr = RapidOCR()
    out_path = OUT / f"part_{lo:04d}_{hi:04d}.txt"
    with open(out_path, "w", encoding="utf8") as f:
        for i in range(lo, hi + 1):
            t0 = time.time()
            try:
                img = page_img(reader, i)
                res, _ = ocr(img)
                text = "\n".join(x[1] for x in (res or []))
                if not text.strip():
                    text = "[OCR EMPTY]"
            except Exception as e:
                text = f"[OCR ERROR: {e!r}]"
            f.write(f"\n\n===== PAGE {i+1} =====\n{text}\n")
            f.flush()
            print(f"page {i+1} done in {time.time()-t0:.1f}s", flush=True)
            gc.collect()
    return str(out_path)

if __name__ == "__main__":
    import pypdf
    n = len(pypdf.PdfReader(PDF).pages)
    nw = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    chunk = (n + nw - 1) // nw
    ranges = [(i, min(i + chunk - 1, n - 1)) for i in range(0, n, chunk)]
    print(f"{n} pages, {len(ranges)} workers", flush=True)
    with mp.Pool(len(ranges)) as pool:
        for p in pool.imap_unordered(worker, ranges):
            print("PART DONE:", p, flush=True)
    print("ALL DONE", flush=True)
