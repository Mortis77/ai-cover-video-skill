---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9da29870b7dfe952a0e458cf6f69e3bd_0411d7bfcd2211f1afbb52540064ee0f
    ReservedCode1: whkmM59Selj4HLqRJdYnzhjUiLl6uv1DXQ7rmGIQRHySZfIr7nUxx/C4XYRd4rEh2OVxE6BrrGZ7EwXJWM/JKpixgttWj61RIh0h4pWdi++8LFrgrr1patZF/nKEYb4IZT+I/im0Gwn3DuDUR07GKLydDHi7GvOAOjojFyThTnodYPC2eZ2K9goYrBs=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9da29870b7dfe952a0e458cf6f69e3bd_0411d7bfcd2211f1afbb52540064ee0f
    ReservedCode2: whkmM59Selj4HLqRJdYnzhjUiLl6uv1DXQ7rmGIQRHySZfIr7nUxx/C4XYRd4rEh2OVxE6BrrGZ7EwXJWM/JKpixgttWj61RIh0h4pWdi++8LFrgrr1patZF/nKEYb4IZT+I/im0Gwn3DuDUR07GKLydDHi7GvOAOjojFyThTnodYPC2eZ2K9goYrBs=
---

# SKILL: ai-cover-video

**AI 翻唱 KTV 视频全流程制作技能**（音频制作 → 歌词打轴 → KTV 成片渲染）

## 适用场景

- 把任意歌曲做成 **AI 翻唱视频**：原曲下载 → 人声/伴奏分离 → RVC 变声（换声线）→ 混音 → 歌词打轴 → 背景图 + KTV 五行滚动歌词渲染成 MP4。
- 典型需求："把《XX》用 XX 声线翻唱做成视频"、"给我做个 KTV 版 MV"、"五行同屏滚动歌词成片"。
- 已在本机验证的两条真实链路：**《上海滩》粤语翻唱**（KTV 右对齐五行滚动）、**《天下》初华翻唱**（KTV 居中偏右五行滚动 + 分段渲染 concat）。

## 完整流程总览

```
┌────────────────────────────────────────────────────────────────┐
│ 第 1 步  音频制作 (01_audio_制作音频.md)                         │
│   原曲下载 → 转 wav → UVR5 分离人声/伴奏 → RVC 变声(换声线,    │
│   男歌女唱升调) → 人声/伴奏混音 → 翻唱音频.wav                  │
├────────────────────────────────────────────────────────────────┤
│ 第 2 步  歌词打轴 (02_lyrics_打轴.md)                            │
│   faster-whisper 词级 ASR(用整首正确歌词作 initial_prompt) →    │
│   歌词行 ↔ 词级时间戳 difflib 对齐 → 逐句 SRT(重复段按演唱顺序) │
├────────────────────────────────────────────────────────────────┤
│ 第 3 步  成片渲染 (03_render_成片.md)                            │
│   背景构图分析(字幕放留白侧/歌名放人物对侧) → ffmpeg drawtext   │
│   KTV 五行同屏滚动 → 分段渲染 + concat → 成片.mp4               │
└────────────────────────────────────────────────────────────────┘
```

- 每一步都有独立文档 + 参数化模板脚本（`templates/`），脚本内所有路径为占位符 `{XXX}`，注释中附《上海滩》《天下》真实示例值。
- 执行时**建议按 01 → 02 → 03 顺序**，每步产出物是下一步的输入。

## 前置依赖清单

### 工具链（本机已验证路径）

| 组件 | 用途 | 本机路径示例 |
|---|---|---|
| ffmpeg | 渲染/混音/切片 | `C:\path\to\ffmpeg.exe` |
| UVR5 (RVC Core) | 人声/伴奏分离 | `E:\path\to\RVC_Core`（含 `infer/modules/uvr5/modules.py`） |
| RVC (RVC Core) | 变声推理 | `E:\path\to\RVC_Core`（`infer/modules/vc/modules.py`） |
| faster-whisper | 歌词 ASR 打轴 | pip 安装（cuda float16 或 cpu int8） |
| 本机工具链 Python | 混音/重采样 | 含 `librosa + soundfile` 的环境（模板用 `templates/audio_pipeline_template.py` 中声明的解释器） |
| 字体 | drawtext 渲染 | `simkai.ttf`（楷体，系统字体） |

### Python 依赖

- 音频：`librosa` `soundfile` `numpy` `scipy`
- ASR：`faster-whisper`（模型 large-v3 / small 自动下载）
- 变声：UVR5 / RVC 各自自带环境（无需手动 pip），仅需保证 `cublas64_12.dll` 可见（见 04 踩坑清单）

### 素材清单

| 素材 | 占位符 | 说明 |
|---|---|---|
| 原曲音频 | `{ORIGINAL_AUDIO}` | m4a/mp3/wav 均可，先转 44.1k wav |
| 声线模型 | `{VOCAL_MODEL}` | RVC `.pth`，如 `chuhua.pth` |
| 分离模型 | `{UVR5_MODEL}` | 如 `HP5_only_main_vocal` |
| 背景图 | `{BG_IMAGE}` | 1920x1080 或 4:3/竖图均可（脚本自动 cover 铺满） |
| 歌词文本 | `{LYRICS_FULL}` | 整首正确歌词（含重复段），作 ASR initial_prompt 与对齐基准 |

### 环境变量（ASR / RVC 通用，模板已内置）

```
HF_ENDPOINT=https://hf-mirror.com
HF_HUB_DISABLE_XET=1
HF_HUB_DISABLE_TELEMETRY=1
# RVC 推理额外需要 torch 的 dll 目录在最前：
PATH = <RVC_Core>;<torch\lib>;<原 PATH>
```

## 真实示例（本机已验证）

| 项 | 《上海滩》 | 《天下》 |
|---|---|---|
| 原曲 | `temp\shanghaitan\shanghaitan_origin.m4a`（粤语） | `temp\tianxia\tianxia_origin.m4a` |
| 分离模型 | `HP5_only_main_vocal` | `HP5_only_main_vocal` |
| 声线模型 | 粤语女声线（如 `chuhua.pth` 同族） | `chuhua.pth`（初华，+3 半音） |
| 翻唱混音 | `temp\shanghaitan_mix3.wav`（194.18s） | `output\tianxia_mix.wav`（221.2s，vg=1.15/ig=1.0/peak=0.95） |
| ASR | `temp\shanghaitan_asr_v2.srt`（12 句） | `temp\tianxia_asr.srt`（44 行，27.89s–213.78s） |
| 背景图 | `C:\path\to\bg_image_1.jpg` | `C:\path\to\bg_image_2.jpg`（1024x768 人物偏左） |
| 渲染脚本 | `temp\render_sht_gen8.py`（右对齐） | `temp\render_tianxia_v2.py`（居中偏右，分段+concat） |
| 成片 | `output\shanghaitan_final.mp4` | `output\tianxia_final.mp4` |

## 产物文件说明

- 本 skill 目录结构：
```
ai_cover_video_skill/
├── SKILL.md                      本文件
├── 01_audio_制作音频.md          音频制作流程 + 模板使用说明
├── 02_lyrics_打轴.md             ASR 打轴流程 + 模板使用说明
├── 03_render_成片.md             成片渲染流程 + 模板使用说明
├── 04_gotchas_踩坑清单.md        本机已验证全部坑位
└── templates/
    ├── audio_pipeline_template.py   UVR5 分离 + RVC 变声 + 混音 一体化模板
    ├── asr_lyrics_template.py       词级 ASR + 歌词行对齐生成 SRT 模板
    └── render_ktv_template.py       KTV 五行同屏滚动渲染模板（分段+concat）
```
*（内容由AI生成，仅供参考）*
