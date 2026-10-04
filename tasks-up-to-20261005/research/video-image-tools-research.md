# 图片与视频处理工具 —— 工具选型调研

- **调研范围**：① 图片内容识别（检测/分割、OCR、图像描述与打标、多模态视觉问答）② 图片编辑与拼接（拼接、抠图、超分、修复、去水印、批量格式与元数据）③ 视频处理（FFmpeg 获取、GUI 剪辑、视频理解、中文语音转字幕、下载与压缩）④ 一体化编排（本地推理运行时、Transformers/Gradio、ComfyUI/n8n/Dify）以及商业云 API 的价格与隐私边界。
- **一手来源与核对方式**（本报告所有事实按下面四类来源标注，不用二手榜单下结论）：
  1. **官方文档/README 原文**：`web_fetch` 读取官方文档页与 `raw.githubusercontent.com` 上的仓库 README / LICENSE 原文。
  2. **结构化仓库元数据**：GitHub REST API（`api.github.com/repos/<owner>/<repo>`，取 `stargazers_count` / `license.spdx_id` / `archived` / `pushed_at`）。本次共核对 60 个仓库。
  3. **PyPI / Hugging Face 官方 JSON API**：`pypi.org/pypi/<pkg>/json`（版本、requires_python）、`huggingface.co/api/models/<id>`（license、gated、downloads）。
  4. **本机实测**：在本机 Windows 11 上实跑 `winget search`、`ffmpeg -version / -encoders / -filters`、以及 DSH 内置 Python 的 `importlib.util.find_spec` 探针。**表中 winget 包 ID 与版本号全部来自本机 `winget search` 输出，未凭记忆书写。**
- **版本与时效**：调研时间 **2026-10（本会话）**。GitHub 元数据为 2026-10-04 当天抓取；winget 搜索结果同月；Python 包版本来自当日 PyPI。星数会漂移，**星数只作量级参考，不要当结论**。
- **本机环境实测结论（直接影响选型）**：
  - 已装：`ffmpeg.exe` → `D:\Programmer\ffmpeg-essentials\bin\ffmpeg.exe`（`ffmpeg version 2025-12-01-git-7043522fe0-essentials_build-www.gyan.dev`）；`winget` 可用。
  - **未装**：ImageMagick、ExifTool（实测 `Get-Command magick / exiftool` 均无结果）。
  - **已实测跑通的最小流水线**：Pillow 网格拼接、FFmpeg `tile` 联络图、`hstack` 并排、抽封面，四条命令全部在本机成功产出文件（详见 §3.1 的实测说明）。
  - **注意 `python` 的 PATH 陷阱**：PATH 上的 `python` 是 `D:\msys64\mingw64\bin\python.exe`，**没有 pip**。真正可用的是 DSH 内置发行版 `C:\Users\29580\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`（**Python 3.12.14，pip 26.2.1**，自带 Pillow 12.3.0 / numpy 2.3.5 / pandas 3.0.1 / lxml / openpyxl / python-docx / python-pptx，且 **tkinter、venv、ssl 齐全**）。
  - **该内置 Python 当前没有任何 CV/ML 包**：`cv2`、`torch`、`transformers`、`onnxruntime`、`skimage`、`pytesseract`、`paddleocr`、`rembg`、`faster_whisper`、`av`、`imageio_ffmpeg` 全部 `MISSING`（实测探针）。所以本报告里所有 pip 类工具都需要**新建 venv 后安装**，这是最关键的落地前提。

---

## TL;DR（结论先行）

1. **先装三件套，成本最低、覆盖面最广**：`winget install Gyan.FFmpeg.Essentials`（已有等价构建）、`winget install ImageMagick.ImageMagick`、`winget install OliverBetz.ExifTool`。这三个 CLI 都是 agent 可直接批调的，**图片拼接、批量格式转换、元数据清理、抽帧、压缩、烧字幕基本一次到位**，且全部可离线。
2. **图片拼接按"有没有重叠"分流，不要用一种工具硬扛**：有重叠/要全景 → **OpenCV Stitcher**；无重叠规则网格 → **ImageMagick `montage`**；等尺寸批量拼或视频帧联络图 → **FFmpeg `hstack/vstack/xstack/tile`**。三条路线官方文档均已核对（见 §3.1）。
3. **中文 OCR 主推 PaddleOCR，轻量替代 RapidOCR，GUI 兜底 Umi-OCR**：PaddleOCR 3.x 已到 **PP-OCRv6 / PaddleOCR-VL**，Apache-2.0，中文与文档解析（表格/公式/版面）明显强于其它开源方案；但 PaddlePaddle 在 Windows 的安装链较重。**RapidOCR（Apache-2.0，onnxruntime 后端）是"不装 paddle 也能跑中文 OCR"的最省事路线**；**Umi-OCR（MIT，4.7 万星）适合人手点一下的批量离线 OCR**。Tesseract 中文精度已不是第一梯队，仅建议用于英文/多语种纯文本或已有流水线。
4. **本地视觉理解首选 Ollama + Qwen3-VL（Apache-2.0）**：`ollama run` 直接吃图片，`/api/chat` 与 OpenAI 兼容端点都能被 agent 调用；Qwen3-VL-8B-Instruct / Qwen2.5-VL-7B-Instruct 模型卡均为 **Apache-2.0、无 gating**，商用最省心。要 GUI 就用 LM Studio（`winget install ElementLabs.LMStudio`）。
5. **中文语音转字幕 = `faster-whisper`（MIT，CTranslate2）或 `whisper.cpp`（MIT，CPU/GPU 皆可）**；中文识别质量要求更高时补 **FunASR / SenseVoice**（阿里达摩院，MIT）。字幕烧录用本机 ffmpeg 的 `subtitles` 滤镜（已实测存在），**Windows 下字体路径要转义**（见 §4.4）。
6. **图像编辑"重活"看 GPU**：抠图 **rembg**（MIT）/ **BiRefNet**（MIT）可 CPU 跑；超分 **Upscayl**（AGPL-3.0）**硬要求 Vulkan GPU**（多数集显/纯 CPU 不可用），无 GPU 请改用 Real-ESRGAN 的 CPU 路径或直接 Pillow/OpenCV 常规缩放。
7. **License 风险集中在四处**：**Ultralytics YOLO = AGPL-3.0**（商用闭源需买企业授权）；**insightface 代码 MIT 但预训练模型仅限非商用研究**；**CodeFormer = S-Lab License 1.0（明确仅非商用）**；**GFPGAN 本体 Apache-2.0 但含 CC BY-NC-SA 4.0 的第三方组件**。这些**不要**直接用在商业交付里。
8. **一体化编排按"你要什么"选**：要**图像/视频生成与编辑工作流** → ComfyUI（GPL-3.0，有本地 API，已支持 Qwen3-VL/SAM 3/BiRefNet 节点）；要**把多个服务串成自动化定时任务** → n8n（注意其 Sustainable Use License 不是标准开源协议）；要**给自家脚本套一个 Web UI** → Gradio（`pip install gradio`，最快）；Dify 适合做 LLM 应用/RAG，不是图像流水线工具。

---

## 1. 一页速览对比表

> 「Windows 安装」列全部为本机 `winget search` 实测出的**确切包 ID**；License 以官方 LICENSE/仓库元数据为准；链接给到具体页面。

| 工具 | 类别 | 平台 | License | Windows 安装（确切命令） | 最适合干什么 | 官方链接 |
|---|---|---|---|---|---|---|
| **FFmpeg** (Gyan build) | 视频/图像 CLI | Win/Linux/mac | LGPL/GPL（视构建，Gyan 为 GPL） | `winget install Gyan.FFmpeg.Essentials`（或 `Gyan.FFmpeg` 全量） | 转码、抽帧、拼接、压缩、烧字幕、去 logo——**一切音视频底座** | [ffmpeg.org/download.html](https://ffmpeg.org/download.html) |
| **ImageMagick** | 图像 CLI | 全平台 | ImageMagick License（Apache-2.0 风格，非 SPDX 标准名） | `winget install ImageMagick.ImageMagick` | 规则网格拼贴 `montage`、`+append`、批量 `mogrify`、格式转换 | [imagemagick.org/montage/](https://imagemagick.org/montage/) |
| **ExifTool** | 元数据 CLI | 全平台 | Perl Artistic / GPL | `winget install OliverBetz.ExifTool` | 批量读改写 EXIF、清 GPS 隐私、按拍摄日期改名 | [exiftool.org](https://exiftool.org/) |
| **Pillow** | 图像库 | 全平台 | MIT-CMU（HPND） | DSH 内置 Python **已自带 12.3.0** | 脚本化拼接/绘制/格式批处理，零安装成本 | [pillow.readthedocs.io](https://pillow.readthedocs.io/en/stable/) |
| **OpenCV (opencv-python)** | 视觉库 | 全平台 | Apache-2.0 | `pip install opencv-python`（PyPI latest **5.0.0.93**） | `cv2.Stitcher` 全景拼接、读图写图、DNN 推理 | [docs.opencv.org/4.x/d8/d19/tutorial_stitcher.html](https://docs.opencv.org/4.x/d8/d19/tutorial_stitcher.html) |
| **PaddleOCR** | OCR | Win/Linux/mac | Apache-2.0 | `pip install paddlepaddle paddleocr` | **中文 OCR + 文档解析（表格/公式/版面）SOTA** | [github.com/PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) |
| **RapidOCR** | OCR | 全平台 | Apache-2.0 | `pip install rapidocr onnxruntime`（旧名 `rapidocr-onnxruntime` 最新 1.4.4） | 不装 paddle 的轻量中文 OCR，ONNX/CPU 友好 | [rapidai.github.io/RapidOCRDocs](https://rapidai.github.io/RapidOCRDocs/) |
| **Umi-OCR** | OCR GUI | Windows/Linux | MIT | GitHub Releases 下载便携版（无 winget 官方包） | **人手批量离线 OCR**，截图/PDF/批量，中文开箱即用 | [github.com/hiroi-sora/Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) |
| **Tesseract** | OCR | 全平台 | Apache-2.0 | `winget install UB-Mannheim.TesseractOCR`（5.4.0）或 `winget install tesseract-ocr.tesseract`（5.5.3） | 英文/多语种纯文本 OCR，老流水线兼容 | [tesseract-ocr.github.io/tessdoc/Installation.html](https://tesseract-ocr.github.io/tessdoc/Installation.html) |
| **Ollama** | 本地推理 | Win/Linux/mac | MIT | `winget install Ollama.Ollama`（0.35.1） | 一条命令跑本地视觉/语言模型，HTTP 可被 agent 调 | [docs.ollama.com/capabilities/vision](https://docs.ollama.com/capabilities/vision) |
| **LM Studio** | 本地推理 GUI | Win/Linux/mac | 免费闭源（有 `lms` CLI） | `winget install ElementLabs.LMStudio`（0.4.25+1） | 图形界面下载/试跑视觉模型，带无头服务模式 | [lmstudio.ai/docs/developer](https://lmstudio.ai/docs/developer) |
| **Qwen3-VL / Qwen2.5-VL** | 多模态模型 | 本地/云 | **Apache-2.0** | 经 Ollama / transformers / vLLM 加载 | 图像描述、OCR、视觉问答、图表理解（中文强） | [huggingface.co/Qwen/Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) |
| **rembg** | 抠图 | 全平台 | MIT | `pip install rembg`（PyPI **2.0.85**，需 Python ≥3.11） | 批量去背景出透明 PNG，CPU 可用 | [github.com/danielgatis/rembg](https://github.com/danielgatis/rembg) |
| **BiRefNet** | 抠图/分割 | 全平台 | MIT | `pip install` 后按官方仓库加载权重 | 高质量二分抠图，细节（发丝/边缘）优于 rembg u2net | [github.com/ZhengPeng7/BiRefNet](https://github.com/ZhengPeng7/BiRefNet) |
| **Upscayl** | 超分 GUI | Win/Linux/mac | **AGPL-3.0** | `winget install Upscayl.Upscayl`（2.15.0） | 图形界面批量放大；**必须有 Vulkan GPU** | [github.com/upscayl/upscayl](https://github.com/Upscayl/upscayl) |
| **Real-ESRGAN** | 超分 | 全平台 | BSD-3-Clause | 官方 ncnn-vulkan 绿色包 / `pip install` | 可脚本化超分；**仓库 2024-08 后无 push，偏停滞** | [github.com/xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) |
| **GFPGAN** | 人脸修复 | 全平台 | Apache-2.0（含 NC 第三方组件） | `pip install gfpgan` | 老照片人脸增强；**2024-07 后无 push** | [github.com/TencentARC/GFPGAN](https://github.com/TencentARC/GFPGAN) |
| **CodeFormer** | 人脸修复 | 全平台 | **S-Lab License 1.0（仅非商用）** | 按官方仓库安装 | 人脸复原质量高，但**商用受限** | [github.com/sczhou/CodeFormer](https://github.com/sczhou/CodeFormer) |
| **IOPaint / lama-cleaner** | 去水印/擦除 | 全平台 | Apache-2.0 | 按官方仓库安装 | 擦除物体/水印，配 LaMa 模型 | [github.com/Sanster/IOPaint](https://github.com/Sanster/IOPaint) |
| **XnConvert** | 批量转换 GUI | Win/mac/Linux | 免费闭源（**商用需买许可**，€15/席起） | `winget install XnSoft.XnConvert`（1.116.0） | 图形界面 500+ 格式批量转换、80+ 动作；可导出到 NConvert CLI | [xnview.com/en/xnconvert/](https://www.xnview.com/en/xnconvert/) |
| **faster-whisper** | 语音转字幕 | 全平台 | MIT | `pip install faster-whisper`（1.2.1） | **中文语音转 SRT 的首选**，CTranslate2 加速 | [github.com/SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| **whisper.cpp** | 语音转字幕 | 全平台 | MIT | 源码 `cmake -B build`（Win 需 MSVC/MinGW） | 纯本地无依赖、CPU/Vulkan/CUDA 皆可，含 `whisper-server` | [github.com/ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) |
| **FunASR / SenseVoice** | 中文 ASR | 全平台 | MIT | `pip install funasr`（1.4.16） | 中文/方言识别与标点，国内场景调优 | [github.com/modelscope/FunASR](https://github.com/modelscope/FunASR) |
| **yt-dlp** | 视频下载 | 全平台 | Unlicense | `winget install yt-dlp.yt-dlp`（2026.08.19） | 下载 B 站/抖音等素材（**注意平台条款与版权**） | [github.com/yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| **HandBrake** | 视频转码 | Win/mac/Linux | GPL-2.0 | `winget install HandBrake.HandBrake`（1.11.2）/ `HandBrake.HandBrake.CLI` | GUI 压缩转码，预设友好 | [handbrake.fr/downloads.php](https://handbrake.fr/downloads.php) |
| **LosslessCut** | 无损剪切 | Win/mac/Linux | GPL-2.0 | `winget install ch.LosslessCut`（3.69.0） | 不重编码快速裁剪/合并，秒级完成 | [github.com/mifi/lossless-cut](https://github.com/mifi/lossless-cut) |
| **Shotcut** | 剪辑 GUI | Win/mac/Linux | GPL-3.0 | `winget install Meltytech.Shotcut`（26.9.27） | 免费开源非线性剪辑，无账号无联网 | [shotcut.org/download/](https://shotcut.org/download/) |
| **Kdenlive** | 剪辑 GUI | Win/mac/Linux | GPL-3.0 | `winget install KDE.Kdenlive`（26.08.1） | 功能更全的开源剪辑，Win 版官方支持 | [kdenlive.org/download/](https://kdenlive.org/download/) |
| **剪映专业版** | 剪辑 GUI | Win/mac | 免费闭源（会员增值；**账号+联网**） | `winget install ByteDance.JianyingPro`（11.5.0.14471） | 中文模板/自动字幕最省事；**素材上传云端的隐私需自评** | [capcut.com/download](https://www.capcut.com/download) |
| **DaVinci Resolve** | 剪辑/调色 GUI | Win/mac/Linux | 免费版闭源；Studio 一次性付费 | 官网下载（**winget 无官方包**） | 专业调色与剪辑，免费版功能已很强 | [blackmagicdesign.com/products/davinciresolve](https://www.blackmagicdesign.com/products/davinciresolve) |
| **Shutter Encoder** | 转码 GUI | Win/mac/Linux | 免费（donationware） | `winget install PaulPacifico.ShutterEncoder`（20.4） | FFmpeg 的图形外壳，参数暴露充分 | [shutterencoder.com/download/](https://www.shutterencoder.com/download/) |
| **ComfyUI** | 节点式工作流 | Win/Linux/mac | **GPL-3.0** | `winget install Comfy.ComfyUI-Desktop`（1.1.6）或 portable 7z | 图像/视频生成与编辑流水线，带本地 API | [github.com/comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) |
| **Transformers** | 模型加载框架 | 全平台 | Apache-2.0 | `pip install transformers`（5.18.0） | 统一加载检测/分割/CLIP/VLM/OCR 模型 | [huggingface.co/docs/transformers](https://huggingface.co/docs/transformers/index) |
| **Gradio** | 自建 Web UI | 全平台 | Apache-2.0 | `pip install gradio`（6.29.1） | 给自家脚本最快套一个可分享的 Web 界面 | [gradio.app/docs](https://www.gradio.app/docs) |
| **n8n** | 工作流编排 | 自托管/Docker | **Sustainable Use License（非 OSI）**；Cloud 付费 | Docker / `npx n8n`（**winget 无包**） | 定时把 OCR/转码/上传等步骤串成自动化 | [docs.n8n.io/n8n-community-license/…/license-faq](https://docs.n8n.io/n8n-community-license/community-license/license-faq) |
| **Dify** | LLM 应用平台 | 自托管/Docker | 开源版 + 商用条款（**需读官方许可**） | Docker Compose（官方文档） | RAG/Agent 应用编排，**非图像流水线首选** | [github.com/langgenius/dify](https://github.com/langgenius/dify) |

---

## 2. 图片内容识别（视觉理解）

### 2.1 通用物体/场景检测与分割

| 项目 | stars（2026-10-04） | License | 最近 push | 说明 |
|---|---|---|---|---|
| [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | 62,180 | **AGPL-3.0** | 2026-10-04 | YOLO 家族事实标准，开箱训练/推理/导出 ONNX；**AGPL 是最大坑** |
| [facebookresearch/detectron2](https://github.com/facebookresearch/detectron2) | 34,755 | Apache-2.0 | 2026-09-30 | 检测/分割/关键点老牌框架；**未归档**，但社区普遍认为新项目应转向 Transformers/MMDetection |
| [opencv/opencv](https://github.com/opencv/opencv) | 91,056 | Apache-2.0 | 2026-10-02 | `cv2.dnn` 可直接加载 ONNX 做检测推理，零额外依赖 |

**建议**：只想"跑个检测拿框"→ `ultralytics` 最省事（`pip install ultralytics`，PyPI 8.4.172），但**先确认 AGPL 是否可用**；要宽松许可 → ONNX 模型 + `onnxruntime`，或用 Transformers 的 DETR/RT-DETR/SAM 系。
**不确定性**：Ultralytics 的商业授权条款与价格按其官网 Enterprise License 页为准，本报告**未核实具体价格**。

### 2.2 OCR

| 方案 | License | 中文 | 安装 | 关键结论 |
|---|---|---|---|---|
| **PaddleOCR** | Apache-2.0 | ★★★★★ | `pip install paddlepaddle paddleocr`（PyPI paddleocr 3.7.0 / paddlepaddle 3.3.1） | 已演进到 **PP-OCRv6**（单模型覆盖中英日+46 拉丁语系，官方称 tiny 1.5M / small 7.7M / medium 34.5M 三档）与 **PaddleOCR-VL-1.6（0.9B 文档解析 VLM）**；官方 README 声称 PP-OCRv6 medium 在检测/识别上超越主流 VLM（含"Qwen3-VL-235B / GPT-5.5"这类对比——**该对比属官方自述，本报告未独立复核**）；Python 支持面标注 3.8~3.12，**与本机 3.12.14 吻合** |
| **RapidOCR** | Apache-2.0 | ★★★★ | `pip install rapidocr onnxruntime` | 纯 ONNX Runtime 推理，**不需要 PaddlePaddle**；注意包名变化：`rapidocr-onnxruntime` 停在 1.4.4（`requires_python <3.13`），新包名为 `rapidocr`（3.9.2） |
| **Umi-OCR** | MIT | ★★★★★ | GitHub Releases 便携版 | 47,578★，Windows 图形界面、批量、离线；**适合人手操作**，自动化能力弱于 CLI 方案 |
| **EasyOCR** | Apache-2.0 | ★★★ | `pip install easyocr`（1.7.2） | 上手最快，但需 PyTorch、体积大；**2025-12 后无 push，维护明显放缓** |
| **Tesseract** | Apache-2.0 | ★★ | `winget install UB-Mannheim.TesseractOCR` / `tesseract-ocr.tesseract` | 纯文本场景可靠；**中文精度已落后于 PP-OCR 系** |
| **多模态大模型 OCR** | 视模型 | ★★★★ | 见 §2.3 | 复杂版面/手写/表格更好，但慢且需 GPU 或 API；候选：[GOT-OCR2_0](https://huggingface.co/stepfun-ai/GOT-OCR2_0)（Apache-2.0）、[dots.ocr](https://huggingface.co/dots-studio/dots.ocr)（MIT）、PaddleOCR-VL |

**结论**：中文批量 OCR **默认 PaddleOCR**；装不动 paddle 就 **RapidOCR**；要人点界面就 **Umi-OCR**。

### 2.3 图像描述 / 打标 / 分类 / 检索

| 模型 | License（HF 官方模型卡） | 备注 |
|---|---|---|
| [Qwen/Qwen3-VL-8B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct) | **apache-2.0**，未 gated | 中文视觉理解/OCR/图表首选，8B 级本地可跑 |
| [Qwen/Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct) | **apache-2.0** | 生态成熟、量化版本多 |
| [microsoft/Florence-2-large](https://huggingface.co/microsoft/Florence-2-large) | **mit** | 统一做描述/检测/分割/OCR，模型小、任务全 |
| [Salesforce/blip2-opt-2.7b](https://huggingface.co/Salesforce/blip2-opt-2.7b) | **mit** | 经典图像描述/问答，体量偏大 |
| [vikhyatk/moondream2](https://huggingface.co/vikhyatk/moondream2) | **apache-2.0** | 极小体量 VLM，适合 CPU/边缘打标 |
| [openai/CLIP](https://github.com/openai/CLIP) | MIT（代码）；模型卡未标 license | **以图搜图/零样本分类**：CLIP 向量 + 向量索引即可做素材库检索 |
| [mlfoundations/open_clip](https://github.com/mlfoundations/open_clip) | 仓库元数据 `NOASSERTION`（**需读仓库 LICENSE**） | CLIP 的开源复现与更多权重，训练/微调更灵活 |

**以图搜图路线**：`open_clip`（或 `sentence-transformers` 的 CLIP 封装）提特征 → 存向量 → 用 `faiss`/`sqlite-vec`/numpy 暴力检索。中文语义检索可叠加 [BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5)（MIT）做文本侧。
**人脸**：[deepinsight/insightface](https://github.com/deepinsight/insightface) 29,889★，**代码 MIT，但官方 README 明写"训练数据及其训练出的模型仅限非商用研究"**——商用请换许可明确的人脸模型。

### 2.4 视觉问答 / 本地多模态部署

- **Ollama**（MIT，`winget install Ollama.Ollama`）：官方 [Vision 文档](https://docs.ollama.com/capabilities/vision) 给出 `ollama run gemma4 ./image.png "what is in this image?"`，API 走 `POST http://localhost:11434/api/chat`，`messages[].images` 接受 base64，SDK 可直接传路径/URL/bytes。**agent 集成最省事**。
- **LM Studio**（`winget install ElementLabs.LMStudio`）：官方 [Developer Docs](https://lmstudio.ai/docs/developer) 区分 `lms`（CLI）与无头服务；适合"图形界面选模型 + 命令行调用"。
- **llama.cpp**（MIT，130,237★，2026-10-04 活跃）：`llama-server` 提供本地 HTTP 服务，多模态走 mtmd 路径；Windows 有官方预编译 release。
- **vLLM**：**以 Linux/CUDA 为主要目标平台**，Windows 原生支持不佳（**建议在 WSL2 里用**；本报告未逐条核实 Windows 安装步骤）。Xinference 对 Windows 更友好（元数据见 §5）。

---

## 3. 图片编辑与拼接

### 3.1 「图片拼接」三条路线（本次调研重点，已逐条核对官方文档）

| 路线 | 输入前提 | 适用场景 | 关键 API/命令 | 官方文档 |
|---|---|---|---|---|
| **OpenCV Stitcher** | **相邻图必须有重叠区域** | 全景照片、扫描件拼接（书页/长图分片） | `cv2.Stitcher_create(mode)` + `stitch(imgs)`；`mode` 有 `PANORAMA`（单应/透视）与 `SCANS`（仿射）两类相机模型；**必须检查 `Status` 返回值**，失败时 `pano` 为空 | [tutorial_stitcher](https://docs.opencv.org/4.x/d8/d19/tutorial_stitcher.html) |
| **ImageMagick `montage` / `+append`** | **无重叠**，规则网格 | 素材墙、九宫格、带边框/标签的拼贴画 | `magick montage *.jpg -tile 4x -geometry +5+5 -background '#fff' out.png`；`-append` 纵向、`+append` 横向拼接（不等宽时用 `-background` 填充） | [imagemagick.org/montage/](https://imagemagick.org/montage/) · [command-line-options](https://imagemagick.org/command-line-options/) |
| **FFmpeg `hstack`/`vstack`/`xstack`/`tile`** | 等尺寸（或先 `scale`/`pad` 统一） | **视频帧批量拼**、抽帧联络图（contact sheet）、等尺寸图批量拼接 | `tile` 是"把同一视频的连续帧铺成网格"，`hstack/vstack` 是"多路输入堆叠"，`xstack` 支持自定义布局；四者均在本机 ffmpeg 中实测存在 | [ffmpeg-filters](https://ffmpeg.org/ffmpeg-filters.html)（第 11.128 hstack / 11.257 tile / 11.284 vstack / 11.293 xstack 节） |

**可直接照用的三条命令**（参数取自上述官方文档语义，未编造）：

```powershell
# ① 无重叠规则网格：把当前目录图片拼成每行 4 张、5px 间距的白底拼贴
magick montage *.jpg -tile 4x -geometry +5+5 -background white montage.png

# ② 等尺寸图横向/纵向拼接（ImageMagick 原生 append）
magick a.png b.png c.png +append row.png     # 横向
magick a.png b.png c.png -append  col.png    # 纵向

# ③ 视频抽帧做成联络图（先抽帧，再用 tile 拼格）
ffmpeg -i in.mp4 -vf "fps=1/10,scale=320:-1,tile=4x3" -frames:v 1 contact.png
#   多路视频并排（需等尺寸）
ffmpeg -i left.mp4 -i right.mp4 -filter_complex "[0:v][1:v]hstack=inputs=2[v]" -map "[v]" out.mp4
```

```python
# ④ 有重叠 → OpenCV 全景拼接（务必判 Status）
import cv2
imgs = [cv2.imread(p) for p in ["p1.jpg", "p2.jpg", "p3.jpg"]]
st = cv2.Stitcher_create(cv2.Stitcher_PANORAMA)
status, pano = st.stitch(imgs)
if status == cv2.Stitcher_OK:
    cv2.imwrite("pano.jpg", pano)
else:
    raise RuntimeError(f"stitch failed, status={status}")   # 无重叠时必然失败
```

```python
# ⑤ 纯 Pillow 网格拼接（零依赖，DSH 内置 Python 直接可跑）
from PIL import Image, ImageOps
files = ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]; cols, cell = 2, 512
ims = [ImageOps.exif_transpose(Image.open(f)).convert("RGB") for f in files]
ims = [im.resize((cell, cell)) for im in ims]           # 需要统一尺寸
rows = (len(ims) + cols - 1) // cols
canvas = Image.new("RGB", (cols * cell, rows * cell), "white")
for i, im in enumerate(ims):
    canvas.paste(im, ((i % cols) * cell, (i // cols) * cell))
canvas.save("grid.jpg", quality=92)
```

> **本节命令已实测跑通**（本机 2026-10）：示例 ③ `fps=2,scale=320:-1,tile=4x2` 产出 1280x480 PNG 联络图；`hstack=inputs=2` 两路 640x480 输入并排后输出 1280x480 h264；`-ss 1 -frames:v 1` 抽封面成功；示例 ⑤ Pillow 网格脚本对 4 张不同尺寸图片（800x600 / 640x480 / 500x700 / 900x300）输出 512x512 的 `grid.jpg` 成功。示例 ① ② 需要先装 ImageMagick（本机尚未安装，故未实测）。

> **踩坑提示**：Pillow 打开带 EXIF 旋转的手机照片会**方向错乱**，务必先 `ImageOps.exif_transpose`；超大图注意 `Image.MAX_IMAGE_PIXELS` 的解压炸弹保护会抛 `DecompressionBombError`。OpenCV `Stitcher` 对**无重叠**的规则网格会直接失败（这是设计如此，不是 bug），此类需求请走 montage/FFmpeg。

### 3.2 抠图 / 去背景

| 工具 | License | 说明 |
|---|---|---|
| [rembg](https://github.com/danielgatis/rembg) | **MIT**（24,957★，2026-09-20 活跃） | `pip install rembg`（PyPI 2.0.85，**要求 Python ≥3.11**，本机 3.12.14 满足）；onnxruntime 后端，CPU 可用；批量出透明 PNG |
| [BiRefNet](https://github.com/ZhengPeng7/BiRefNet) | **MIT**（4,246★） | 边缘/发丝质量更好；**注意代码 MIT ≠ 权重许可，需逐个模型卡确认** |
| 商业替代 | 按量计费 | remove.bg 等 SaaS **需要上传图片到云端**，价格与免费额度以官网 pricing 页为准（**本报告未核实具体价格**） |

### 3.3 超分 / 放大

- [Upscayl](https://github.com/upscayl/upscayl)：50,087★，**AGPL-3.0**，`winget install Upscayl.Upscayl`（2.15.0）。官方 README 明确：**需要 Vulkan 兼容 GPU，多数集显与纯 CPU 不可用**；CLI 版本是 [upscayl-ncnn](https://github.com/upscayl/upscayl-ncnn)（**注意：其仓库根目录没有 LICENSE 文件，raw 取 404，实际许可需进一步核实**）。
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)：36,975★，**BSD-3-Clause**，但 **`pushed_at` 停在 2024-08-06，已近两年无提交**——仍可用，但别指望修复与新特性；可脚本化，有 ncnn-vulkan 免安装包。
- waifu2x 系（ncnn-vulkan 版）：**本报告未逐个核实其维护状态与 License**，仅作备选列出。

### 3.4 老照片修复 / 人脸增强

- [GFPGAN](https://github.com/TencentARC/GFPGAN)：37,684★，LICENSE **本体为 Apache-2.0，但同一文件列出第三方组件含 CC BY-NC-SA 4.0（源自 DFDNet）**；`pushed_at` 2024-07-26（停滞）。
- [CodeFormer](https://github.com/sczhou/CodeFormer)：18,171★，LICENSE 原文为 **"S-Lab License 1.0 … Redistribution and use for non-commercial purpose"——明确仅限非商用**。
- **两者都建议仅用于个人/研究；商业交付前必须做法务确认。**

### 3.5 去水印 / 物体擦除

- [IOPaint](https://github.com/Sanster/IOPaint)（原 lama-cleaner）：23,310★，Apache-2.0，但 **`archived: true`，已于 2025-04-29 停止维护**。仍可跑，但依赖可能逐渐腐化；长期项目建议直接调用 LaMa 类模型或自建。
- FFmpeg 侧轻量替代：`delogo`（去台标/角标）与 `removelogo` 滤镜**已在本机 ffmpeg 实测存在**，适合固定位置的台标。
- 局部修补类需求若已有 Python，`Pillow + numpy` 的手工修补脚本（本机已有同类 skill：`sh-image-watermark-removal`）往往比装大模型更快。

### 3.6 批量格式转换 / 改名 / 元数据

| 手段 | 适用 | 命令/工具 |
|---|---|---|
| **ImageMagick `mogrify`** | 无 GUI、原地批量处理 | `magick mogrify -resize 1920x1080> -quality 85 -path out *.jpg` |
| **Pillow 脚本** | 需要条件逻辑（按尺寸分流、加水印） | 见 §3.1 示例；DSH 内置 Python 已具备 |
| **XnConvert** | 人手操作 500+ 格式 | `winget install XnSoft.XnConvert`；**个人/教育免费，公司使用必须购买许可（€15/席起，官方页面实测）**；可导出 NConvert CLI 供脚本复用 |
| **ExifTool** | 元数据读改写、**清除 GPS 隐私** | `winget install OliverBetz.ExifTool`（13.59）；`exiftool -all= -overwrite_original img.jpg` 清空全部元数据 |
| **FFmpeg** | 视频封面/抽帧 | `ffmpeg -ss 00:00:03 -i in.mp4 -frames:v 1 cover.jpg` |

---

## 4. 视频处理

### 4.1 FFmpeg 在 Windows 的获取（三条路线，均实测）

| 路线 | 确切命令/地址 | 说明 |
|---|---|---|
| **winget（推荐）** | `winget install Gyan.FFmpeg`（9.0.2，**full**）<br>`winget install Gyan.FFmpeg.Essentials`（9.0.1，**essentials**）<br>`winget install Gyan.FFmpeg.Shared`（9.0.2，共享库版） | 本机实测三者均存在。**已装的 `D:\Programmer\ffmpeg-essentials` 就是 essentials 构建** |
| **gyan.dev 官方构建** | [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) | essentials 与 full 的差异在于**内置编码器/滤镜集合**，官方页面有逐项对照 |
| **BtbN 构建** | `winget install BtbN.FFmpeg.GPL`（或 `.GPL.7.1` / `.GPL.8.0` / `.GPL.8.1` 等分支包） | GPL 静态变体，多版本分支可选 |
| **yt-dlp 专用** | `winget install yt-dlp.FFmpeg` | 若只用 yt-dlp 合流，可只装这个 |

**本机实测的重要事实（可放心用硬件加速）**：现有 essentials 构建的 `configuration` 已启用 `--enable-libx264 --enable-libx265 --enable-nvenc --enable-cuvid --enable-amf --enable-libvpl(qsv) --enable-d3d11va --enable-libass --enable-libfreetype --enable-libfribidi --enable-libzimg`，因此 **libx264/libx265、NVENC、QSV、AMF 硬编、libass 字幕渲染都可用**，无需再换 full 构建。`hstack / vstack / xstack / tile / select / delogo / subtitles / ass / drawtext` 滤镜均已实测存在。

**Python/Node 绑定现状（有坑，勿盲选）**：
- [kkroening/ffmpeg-python](https://github.com/kkroening/ffmpeg-python)：11,011★，Apache-2.0，**但 `pushed_at` 停在 2024-08-04，PyPI 版本仍为 0.2.0，classifiers 只到 Python 3.6**——在 Python 3.12 上属于"能装但无人维护"，**不建议作为新项目依赖**。
- [PyAV-Org/PyAV](https://github.com/PyAV-Org/PyAV)：3,298★，BSD-3-Clause，2026-10-03 活跃（PyPI `av` 19.0.1，`requires_python >=3.12`）——**要 Python 级帧级操作，选 PyAV**。
- [imageio/imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)：303★，BSD-2-Clause，**pushed 2025-01-16**（更新缓慢），胜在"自动下载一份可用 ffmpeg 二进制"，适合快速原型。
- **最稳的姿势**：**直接用 `subprocess` 调本机 `ffmpeg.exe`**，把命令拼成参数数组，绕开所有绑定层。

### 4.2 GUI 剪辑软件

| 软件 | License/价格 | 安装 | 备注 |
|---|---|---|---|
| [Shotcut](https://shotcut.org/download/) | GPL-3.0，免费 | `winget install Meltytech.Shotcut`（26.9.27） | 无账号无联网，活跃维护（2026-10-04 push） |
| [Kdenlive](https://kdenlive.org/download/) | GPL-3.0，免费 | `winget install KDE.Kdenlive`（26.08.1） | 功能更全，Win 版官方提供 |
| [OpenShot](https://github.com/OpenShot/openshot-qt) | GPL 系（仓库 SPDX 未标注） | 官网/winget | 上手简单 |
| **剪映专业版** | 免费 + 会员增值；**需账号、联网上传素材** | `winget install ByteDance.JianyingPro`（11.5.0.14471） | 中文模板与自动字幕最省事；**隐私敏感素材勿用** |
| [DaVinci Resolve](https://www.blackmagicdesign.com/products/davinciresolve) | 免费版；Studio 一次性付费 | 官网下载（**winget 无官方包**，市面上的 `elpideus.DaVinciResolveRPC` 是第三方 RPC 工具，非本体） | 调色能力最强 |
| [LosslessCut](https://github.com/mifi/lossless-cut) | GPL-2.0 | `winget install ch.LosslessCut`（3.69.0） | **无损裁剪/合并**，不重编码，速度极快 |
| [HandBrake](https://handbrake.fr/downloads.php) | GPL-2.0 | `winget install HandBrake.HandBrake` / `.CLI`（1.11.2） | 压缩转码，CLI 版可脚本化 |
| [Shutter Encoder](https://www.shutterencoder.com/download/) | 免费 donationware | `winget install PaulPacifico.ShutterEncoder`（20.4） | FFmpeg 图形外壳 |

### 4.3 视频理解

**通用路线（推荐）**：**FFmpeg 抽帧 + 视觉模型**。抽帧命令：
```powershell
ffmpeg -i in.mp4 -vf "fps=1" frames/%06d.jpg        # 每秒 1 帧
ffmpeg -i in.mp4 -vf "select='gt(scene,0.3)',scale=640:-1" -vsync vfr shots/%04d.jpg  # 镜头切换抽帧
```
抽样后交给 §2.3 的任意 VLM（Qwen3-VL 等）做描述/问答/打标，或交给 ComfyUI 编排。

**长视频专向 VLM**：Qwen 系列的视觉语言模型官方模型卡支持视频输入（**帧数与 token 上限随版本变化，请以具体模型卡为准，本报告未逐版本核实**）。Video-LLaVA 等专用视频模型**本报告未核实其当前维护状态**，仅列作候选。

### 4.4 语音转字幕（中文，重点）

| 方案 | License | 安装 | 特点 |
|---|---|---|---|
| **faster-whisper** | MIT | `pip install faster-whisper`（1.2.1） | CTranslate2 后端，**同精度下比原版 whisper 快且省内存**；CPU 可跑，GPU 更快 |
| **whisper.cpp** | MIT | 源码构建（`cmake -B build`；Win 用 MSVC/MinGW） | 官方 README 核对要点：**`whisper-cli` 默认只吃 16-bit WAV**，其它格式需 `ffmpeg -i in.mp3 -ar 16000 -ac 1 -c:a pcm_s16le out.wav`；支持 **NVIDIA CUDA / Vulkan / OpenVINO / AMD ROCm / Ryzen AI NPU**；内置 **Silero-VAD v6.2.0** 与 `whisper-server`（OpenAI 风格 HTTP）；模型体积 tiny 75MiB → large 2.9GiB |
| **WhisperX** | 见仓库 | `pip install whisperx` | 词级时间对齐 + 说话人分离；**GitHub API 本次被限流，stars/pushed 未核实** |
| **FunASR / SenseVoice** | MIT | `pip install funasr`（1.4.16） | 阿里达摩院，中文/方言与标点更贴合国内场景；模型走 ModelScope |

**推荐组合（中文视频批量加字幕）**：
```powershell
# 1) 抽音轨为 16k 单声道 WAV（whisper.cpp 必需格式；faster-whisper 可直接吃 mp4）
ffmpeg -i in.mp4 -ar 16000 -ac 1 -c:a pcm_s16le audio.wav
# 2) 转写为 SRT（faster-whisper 示例，语言显式指定中文）
python -c "from faster_whisper import WhisperModel; m=WhisperModel('large-v3', device='cpu', compute_type='int8'); segs,_=m.transcribe('audio.wav', language='zh'); open('out.srt','w',encoding='utf-8').write(''.join(f'{i+1}\n{s.start:.3f} --> {s.end:.3f}\n{s.text.strip()}\n\n' for i,s in enumerate(segs)))"
# 3) 烧录字幕（本机 ffmpeg 含 libass，subtitles 滤镜已实测存在）
ffmpeg -i in.mp4 -vf "subtitles=out.srt:force_style='FontName=Microsoft YaHei,FontSize=20'" -c:a copy out_sub.mp4
```
> **Windows 踩坑**：`subtitles` 滤镜的路径会在 ffmpeg 内被二次解析，**盘符冒号与反斜杠必须转义**（例如 `subtitles='C\:/videos/out.srt'`），否则会报找不到文件；中文文件名建议先改名成 ASCII 再处理。字幕**乱码**几乎都是文件未存成 UTF-8 导致。

> 另注：新版 FFmpeg 已内置名为 `whisper` 的音频滤镜（官方 filters 文档第 8.122 节），可把 whisper.cpp 接进滤镜链直接生成字幕——**本机构建是否启用该滤镜未实测（`-filters` 中未见于本次截取片段）**，使用前请用 `ffmpeg -filters | findstr whisper` 确认。

### 4.5 下载 / 压缩 / 封面

- **yt-dlp**：`winget install yt-dlp.yt-dlp`（2026.08.19；另有 nightly 与 GUI 前端 `Stacher`）。**合流需要 ffmpeg**（可装 `yt-dlp.FFmpeg`）。官方仓库 stars/pushed 因本次 API 限流**未核实**。**合规提醒：下载与再分发受平台条款与版权约束，请只处理你有权使用的内容。**
- **压缩**：`ffmpeg -i in.mp4 -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k out.mp4`；追求体积用 `-c:v libx265 -crf 28`；要快且本机有 N 卡用 `-c:v h264_nvenc`（本机构建已启用）。
- **封面**：`ffmpeg -ss 3 -i in.mp4 -frames:v 1 cover.jpg`；要"选最有代表性的一帧"可用 `thumbnail` 滤镜或先抽帧再用视觉模型打分。

---

## 5. 一体化编排与云 API

### 5.1 本地推理运行时（承接 §2.4）

| 运行时 | License | 安装 | 定位 |
|---|---|---|---|
| **Ollama** | MIT（182,131★，2026-10-04 活跃） | `winget install Ollama.Ollama`（0.35.1） | **agent 调用本地视觉/语言模型的最短路径** |
| **LM Studio** | 免费闭源 | `winget install ElementLabs.LMStudio`（0.4.25+1） | GUI 选模型 + `lms` CLI / 无头服务 |
| **llama.cpp** | MIT（130,237★） | 官方 release 预编译 / 自行构建 | 最底层的 GGUF 推理，`llama-server` 供 HTTP |
| **Xinference** | 见仓库 | `pip install xinference` | 统一托管多模型并暴露 API，**Windows 支持优于 vLLM** |
| **vLLM** | Apache-2.0 | **建议 WSL2/Linux** | 高吞吐服务化，**Windows 原生支持不佳（未逐条核实）** |

> 结构化元数据（stars/license/pushed）对 Ollama、llama.cpp、lmstudio-ai/lms、xinference 已抓取；**vLLM / SGLang / Transformers / Gradio / Diffusers / n8n / Dify 因 2026-10-04 当天 GitHub 匿名 API 配额（60 次/小时）耗尽，其 stars 与 `pushed_at` 本轮未核实**，本报告不臆造这些数字。已确认的替代证据：PyPI 上 `transformers 5.18.0`、`gradio 6.29.1` 均为当日最新版。

### 5.2 Python/应用级编排

| 工具 | 安装 | 用途 |
|---|---|---|
| **Transformers** | `pip install transformers`（5.18.0） | 统一加载检测/分割/CLIP/Whisper/VLM；[官方文档](https://huggingface.co/docs/transformers/index) |
| **Gradio** | `pip install gradio`（6.29.1） | **给任何脚本套 Web UI 的最快方式**；[gradio.app/docs](https://www.gradio.app/docs)，注意分享链接会把服务暴露到公网 |
| **Diffusers** | `pip install diffusers` | 扩散模型推理/微调（生成式编辑） |
| **Streamlit** | `pip install streamlit` | 数据/结果看板式界面备选 |

### 5.3 工作流编排

- **ComfyUI**（**GPL-3.0**，LICENSE 原文已核对）：`winget install Comfy.ComfyUI-Desktop`（1.1.6）或官方 portable 7z（nvidia/amd/intel 三版）。官方 README 核对要点：**提供"本地 API 把工作流集成进应用"**；可用 `--offline` 强制离线（关闭付费 API 节点）；原生支持 **SAM 3/3.1、RT-DETRv4、BiRefNet、Depth Anything 3、Qwen3-VL** 等视觉节点，以及 Flux/Qwen-Image 等生成与编辑模型。**定位：图像/视频工作流的可视化编排与批处理。**
- **n8n**（**Sustainable Use License，非 OSI 开源；Cloud 付费**）：自托管走 Docker 或 `npx n8n`，**winget 无官方包（本机实测 "No package found"）**；[官方许可 FAQ](https://docs.n8n.io/n8n-community-license/community-license/license-faq)。**定位：把"下载→转码→OCR→入库→通知"串成定时自动化。**
- **Dify**（开源版 + 商用条款，**具体条款需读官方 LICENSE**）：Docker Compose 部署，PaddleOCR 官方 README 将其列为集成方。**定位：LLM 应用/RAG 编排，不是图像处理流水线。**

### 5.4 商业云 API（价格须以官方 pricing 页为准）

> **本节严格遵守"不编造价格"原则**：下面给出官方 pricing 页地址与计价维度的**定性**说明，**具体数字请打开链接核对当日价格**。本次检索工具只返回了链接列表与零散片段（例如 Gemini 页面片段出现 "$0.50（文本/图像/视频/音频）"与 2027-01-01 生效的 "$2.00" 字样），**片段脱离上下文、无法确认适用模型与生效条件，故不作为结论写入**。

| 服务 | 官方 pricing | 计价维度（定性） | 隐私/联网 |
|---|---|---|---|
| Google Gemini | [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) | 按 token（**图像与视频帧按 token 折算**） | **必须上传**到 Google 云端 |
| OpenAI | [openai.com/api/pricing](https://openai.com/api/pricing/) | 按 token（**图片按分辨率折算 token**） | **必须上传** |
| Anthropic Claude | [anthropic.com/pricing](https://www.anthropic.com/pricing) | 按 token（视觉输入按图像折算） | **必须上传** |
| 阿里云百炼 / 通义千问 | [阿里云百炼模型调用价格](https://www.alibabacloud.com/help/tc/model-studio/model-pricing) | 按 token，分上下文长度档 | **必须上传**；国内合规链路更短 |
| 百度/腾讯/火山 OCR 与视频理解 | 各自官方价格页 | 多为**按调用次数**（每千次） | **必须上传** |
| Azure AI Vision / AWS Rekognition | [azure.microsoft.com/pricing/details/cognitive-services/computer-vision](https://azure.microsoft.com/pricing/details/cognitive-services/computer-vision/) · [aws.amazon.com/rekognition/pricing](https://aws.amazon.com/rekognition/pricing/) | 按调用次数/按图像数 | **必须上传** |

**结论**：**含隐私、含人脸的素材优先本地跑**（Ollama/Qwen3-VL/rembg/PaddleOCR 全部可离线），云 API 只用于"本地模型明显不够"的难例。

---

## 6. 三个典型场景的推荐组合

### 场景 A：批量给图片打标签，建可检索素材库

**目标**：几千张图片 → 每个文件有中文描述/关键词 → 能按自然语言搜图。

```powershell
# 0) 一次性环境（DSH 内置 Python；PATH 上的 msys2 python 没有 pip，务必用全路径）
& "C:\Users\29580\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install open_clip_torch pillow numpy          # CLIP 向量（以图搜图/零样本分类）
```

- **打标（描述+关键词）**：**Ollama + Qwen3-VL**（Apache-2.0，可离线）。`ollama pull` 视觉模型后，循环 `POST http://localhost:11434/api/chat`，`messages[].images` 传 base64，prompt 要求"输出 JSON：描述 + 5 个中文关键词 + 主体类别"。**GPU 不足时**改用 Florence-2（MIT）或 moondream2（Apache-2.0）。
- **检索**：`open_clip` 提图像向量 → 存 `.npy`/faiss；文本侧用 `bge-small-zh-v1.5`（MIT）提中文查询向量，两路对齐后按余弦相似度排序。
- **落库**：`pandas`（已内置）汇总成 CSV/XLSX，或写 sqlite。
- **人工抽检**：Gradio 起一个本地页面看结果（`pip install gradio`）。
- **纯 CPU/无 GPU 兜底**：如果连小模型都跑不动，退化为"目录规则 + 文件 EXIF 时间 + OCR 文本"的元数据检索（PaddleOCR 提图中文字，往往比通用描述更实用）。

### 场景 B：把一组长图拼成网格（三种输入形态）

| 你的输入 | 选什么 | 命令 |
|---|---|---|
| 一组长条截图，**左右有重叠**（如滚动截屏分片） | OpenCV Stitcher `PANORAMA` | §3.1 示例 ④ |
| 一组长条截图，**上下首尾相接但无重叠** | FFmpeg `vstack`（**需先统一宽度**）或 ImageMagick `-append` | `magick *.png -append long.png` |
| 一堆**普通照片**，要排成九宫格缩略图墙 | **ImageMagick `montage`** | `magick montage *.jpg -tile 4x -geometry +5+5 -background white grid.png` |
| 要**带标签/边框/统一裁剪**的精美拼贴 | `montage` + `-label`/`-border`；或 Pillow 脚本精确控制 | 见 §3.1 示例 ⑤ |
| 从**视频**里出联络图 | FFmpeg 抽帧 + `tile` | §3.1 示例 ③ |

**推荐默认**：无重叠先试 `magick montage`（一行命令、自动补齐、支持 500+ 格式）；要精细控制（每格裁剪/水印/圆角）写 Pillow 脚本；只有确认有重叠才上 OpenCV Stitcher。

### 场景 C：给一批视频批量加中文字幕

1. **环境**：`pip install faster-whisper`（MIT）+ 用现成 `ffmpeg.exe`。
2. **转写**：`faster-whisper` `large-v3` 模型，`language='zh'`，`compute_type='int8'`（CPU）或 `float16`（GPU）；输出 SRT（UTF-8）。
3. **质量加强**（可选）：语音是中文口播/方言时补跑 **FunASR / SenseVoice**；需要说话人区分时上 **WhisperX** 的 diarization。
4. **烧录或外挂**：
   - 外挂软字幕（推荐，可再改）：`ffmpeg -i in.mp4 -i out.srt -c copy -c:s mov_text out.mp4`
   - 烧录硬字幕：`ffmpeg -i in.mp4 -vf "subtitles=out.srt:force_style='FontName=Microsoft YaHei,FontSize=20'" -c:a copy out_sub.mp4`（**注意 §4.4 的路径转义坑**）
5. **批量化**：PowerShell 遍历 → 对每个文件跑上面两步；用 `-y` 覆盖、把日志写文件便于 agent 复核。
6. **兜底 GUI**：不想写脚本就用**剪映专业版**的"识别字幕"（中文效果好、免费层可用），但**素材会上传云端**；隐私敏感就用 Shotcut/Kdenlive 手动加 SRT。

---

## 7. 已知坑与不确定性

### 7.1 已用一手来源确认的"硬坑"

1. **Ultralytics YOLO 是 AGPL-3.0**：LICENSE 原文首行即 `GNU AFFERO GENERAL PUBLIC LICENSE Version 3`。**闭源商用产品里直接依赖它，会触发 AGPL 的源码开放义务**（除非购买其企业授权）。
2. **ComfyUI 是 GPL-3.0**：LICENSE 原文确认。自己内部用没问题，**对外分发集成产品时需评估 GPL 传染性**。
3. **CodeFormer 明确非商用**：LICENSE 原文 `S-Lab License 1.0 … for non-commercial purpose`。
4. **GFPGAN 本体 Apache-2.0，但含非商用第三方组件**：LICENSE 内列明源自 DFDNet 的代码为 `CC BY-NC-SA 4.0`。
5. **insightface：代码 MIT，模型非商用**：README 原文——`The code of InsightFace is released under the MIT License… The training data containing the annotation (and the models trained with these data) are available for non-commercial research purposes only.` **自动下载的模型同样受限**。
6. **IOPaint 已归档**：`archived: true`，最后一次 push 2025-04-29。
7. **ffmpeg-python 实际已停滞**：PyPI 最新仍是 `0.2.0`，classifiers 只到 Python 3.6，仓库 2024-08 后无提交。**Python 3.12 项目请改用 PyAV 或直接调 ffmpeg.exe。**
8. **Upscayl 硬依赖 Vulkan GPU**：官方 README 明确"多数 iGPU 与 CPU 不可用"。
9. **OpenCV Stitcher 对无重叠图像必然失败**：官方教程明确要求"检查 Status，失败时 pano 为空"。
10. **whisper.cpp 的 `whisper-cli` 只接受 16-bit WAV**（官方 README 明写）：喂 mp4/mp3 前必须先转。
11. **本机 `python` 是 msys2 的、没有 pip**：所有 `pip install` 必须指向 DSH 内置 Python 的绝对路径，否则一定报 `No module named pip`。
12. **本机内置 Python 无任何 CV/ML 包**（实测 `cv2/torch/transformers/onnxruntime/skimage/pytesseract/paddleocr/rembg/faster_whisper/av/imageio_ffmpeg` 全 MISSING）：**本文所有 pip 方案都要先建 venv 安装**。
13. **XnConvert 商用要付费**：官方页面写明个人/教育免费，**公司使用必须购买许可**（页面列出 €15/席起的分档）。
14. **n8n 不是标准开源许可**：官方文档称 Sustainable Use License；**且 winget 无官方包**（本机实测无结果）。
15. **ImageMagick / Pillow / scikit-image / FFmpeg / HandBrake 在 GitHub 元数据里是 `NOASSERTION`**：这**不代表无许可**，而是 GitHub 无法把其 LICENSE 文本匹配到 SPDX 模板（例如 ImageMagick License、Pillow 的 MIT-CMU/HPND、FFmpeg 的 LGPL/GPL 双轨）。**选用时请读仓库 LICENSE 原文，别只看元数据。**

### 7.2 显式标注的"未核实"项（不要当结论用）

- **云 API 具体价格**：本次检索只取到官方 pricing 页链接与零散片段，**未取到可确认的完整价目表**，故全文只给计价维度与官方链接，**不给数字**。
- **GitHub stars / pushed_at 未核实**：`m-bain/whisperX`、`modelscope/FunASR`、`yt-dlp/yt-dlp`、`openai/whisper`、`comfyanonymous/ComfyUI`、`huggingface/transformers`、`gradio-app/gradio`、`huggingface/diffusers`、`n8n-io/n8n`、`langgenius/dify`、`vllm-project/vllm`、`xorbitsai/inference` —— 2026-10-04 当天 GitHub 匿名 API 配额耗尽（60/hr），这些仓库的星数与最近提交时间**本轮未核实**。
- **版本号会变**：本文中的 winget/pip 版本号均为 2026-10 当天实测值，**装之前请再跑一次 `winget search` / `pip index versions`**。
- **包名变更风险**：RapidOCR 已从 `rapidocr-onnxruntime`（停在 1.4.4，`requires_python <3.13`）转向 `rapidocr`（3.9.2）；Tesseract 有 `UB-Mannheim.TesseractOCR`（5.4.0）与 `tesseract-ocr.tesseract`（5.5.3）两个不同来源的包。
- **模型权重许可 ≠ 代码许可**：rembg、BiRefNet、Real-ESRGAN、Upscayl 的**代码**许可已核实，但**具体权重文件**可能另有条款；商用前请逐个模型卡确认。
- **upscayl-ncnn 的许可未确认**：仓库根目录无 LICENSE（raw 取 404）。
- **waifu2x 系与 Video-LLaVA 系**：仅作为候选列出，**维护状态与许可本轮未核实**。
- **vLLM 在 Windows 的可用性**：普遍建议 WSL2，但**本轮未核实官方是否有 Windows 原生安装说明**。
- **PaddleOCR README 中的性能对比**（如"超越 Qwen3-VL-235B / GPT-5.5"、OmniDocBench 96.3%）**属官方自述**，本报告未做独立复现。
- **FFmpeg 的 `whisper` 滤镜**：官方 filters 文档存在该节，但**本机构建是否启用未实测**。

### 7.3 给 agent 自动化的接线建议（本会话经验）

- **优先 CLI 而非 Python 绑定**：`ffmpeg.exe`、`magick`、`exiftool` 用 `subprocess`/参数数组调用，比任何 Python 包装层都稳（ffmpeg-python 已停滞是活例子）。
- **pip 装到独立 venv**：不要污染 DSH 内置 Python 的 site-packages（内置只保证 numpy/pandas/Pillow 等，且是 DSH 运行时资产）。
- **长任务写日志**：转码/OCR/转写都是分钟级，把 stdout/stderr 落盘，agent 才能复查失败原因。
- **大模型第一次运行要下权重**：Ollama/whisper/PaddleOCR 首次调用会下载数 GB 模型，**"离线可用"指的是下载之后**；批量任务前先预热一次。
- **路径与编码**：中文文件名 + 空格在 FFmpeg 滤镜参数里极易出错，**批处理前统一重命名为 ASCII**，字幕文件一律 UTF-8。
