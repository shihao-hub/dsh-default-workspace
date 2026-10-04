import io, sys, time
import pypdf
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

PDF = r'D:\BaiduNetdiskDownload\面向对象分析与设计  第3版  修订版_14364870.pdf'
OUT = r'C:\Users\29580\Documents\deepseek-harness\default-workspace\ooad_text.txt'

ocr = RapidOCR()
reader = pypdf.PdfReader(PDF)
n = len(reader.pages)
with open(OUT, 'w', encoding='utf-8') as f:
    for i, page in enumerate(reader.pages):
        t0 = time.time()
        try:
            im = Image.open(io.BytesIO(page.images[0].data)).convert('RGB')
            result, _ = ocr(im)
            text = "\n".join(x[1] for x in (result or []))
        except Exception as e:
            text = f"[OCR ERROR: {e}]"
        f.write(f"\n\n===== PAGE {i+1} =====\n{text}")
        f.flush()
        print(f"page {i+1}/{n} {time.time()-t0:.1f}s chars={len(text)}", flush=True)
print("DONE", flush=True)
