# /// script
# requires-python = ">=3.10"
# dependencies = ["faster-whisper", "av<16"]
# ///
"""诊断用：关掉 VAD 转写，判断音轨里到底有没有人声。"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from faster_whisper import WhisperModel  # noqa: E402

wav = sys.argv[1]
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe(
    wav, language="zh", vad_filter=False, beam_size=5, condition_on_previous_text=False
)
print(f"lang={info.language} p={info.language_probability:.2f}", flush=True)
n = 0
for seg in segments:
    n += 1
    print(f"[{seg.start:7.2f} -> {seg.end:7.2f}] nsp={seg.no_speech_prob:.2f} {seg.text.strip()}", flush=True)
print(f"segments={n}")
