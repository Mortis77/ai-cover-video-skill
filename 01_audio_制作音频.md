---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9da29870b7dfe952a0e458cf6f69e3bd_0a123c72cd2211f1afbb52540064ee0f
    ReservedCode1: GZux1hj602B9R0vK2SNn1pqzNTwL1FqIJCbRzT0pOJZA71KuNyweTzxNV33N3zsgTJLxkt6NGO4rst2zNzRnxV/ZnIg2fm48obfCFoYum8difUpRFbxc8oPx2xjZvGPUjUFt7DYP78mIJTU+PpsJVd8WdRXGc9Y3UmBPD2C3fvS8nctdomW2JvpWoc4=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9da29870b7dfe952a0e458cf6f69e3bd_0a123c72cd2211f1afbb52540064ee0f
    ReservedCode2: GZux1hj602B9R0vK2SNn1pqzNTwL1FqIJCbRzT0pOJZA71KuNyweTzxNV33N3zsgTJLxkt6NGO4rst2zNzRnxV/ZnIg2fm48obfCFoYum8difUpRFbxc8oPx2xjZvGPUjUFt7DYP78mIJTU+PpsJVd8WdRXGc9Y3UmBPD2C3fvS8nctdomW2JvpWoc4=
---

# 01 音频制作（下载 → 分离 → 变声 → 混音）

> 模板脚本：`templates/audio_pipeline_template.py`（UVR5 分离 + RVC 变声 + 混音一体化）。
> 真实链路参考：《天下》初华翻唱（`temp\tianxia\uvr5_sep_tx.py` → `temp\tianxia\rvc_infer_tx.py` → `output\tianxia_mix.wav`）。

## 1. 流程图

```
原曲下载({ORIGINAL_AUDIO})
   │  mp3_to_wav / librosa 转 44.1k wav ({ORIGINAL_WAV})
   ▼
UVR5 分离（模型 {UVR5_MODEL}，如 HP5_only_main_vocal）
   ├── {WORK_DIR}\uvr5_out\vocal\{VOCAL_ORIGIN}.wav       人声（原始声线）
   └── {WORK_DIR}\uvr5_out\ins\{INSTRUMENTAL}.wav         伴奏
   ▼
RVC 变声（模型 {VOCAL_MODEL}，f0_up_key={F0_UP_KEY}）
   └── {WORK_DIR}\{VOCAL_CONVERTED}.wav（48k）→ 重采样 44.1k（{VOCAL_CONVERTED_44K}）
   ▼
混音（--vg {VOCAL_GAIN} --ig {INST_GAIN} --peak {PEAK}）
   └── {OUTPUT_DIR}\{MIX_OUT}.wav  ← 最终翻唱音频（下一步 ASR / 渲染输入）
```

## 2. 前置环境（一次性）

- UVR5 / RVC 共用 `RVC_Core` 目录（本机 `E:\path\to\RVC_Core`），脚本内需：
  - `os.chdir(core)` + `sys.path.insert(0, core)`
  - `PATH` 前置 `core` 和 `core\..\Runtime\Lib\site-packages\torch\lib`（缺 `cublas64_12.dll` 会 ImportError，见 04）
  - `load_dotenv(core\.env)`（配置数据库等）
- HF 镜像环境变量（faster-whisper 用，见 SKILL 前置依赖）。

## 3. 步骤详解

### 3.1 下载原曲并转 wav

- 用浏览器/下载工具获取原曲（`{ORIGINAL_AUDIO}`，m4a/mp3 均可）。
- 转 44.1k 立体声 wav：
  ```bash
  ffmpeg -y -i "{ORIGINAL_AUDIO}" -ar 44100 -ac 2 "{ORIGINAL_WAV}"
  ```
  或模板内 `to_wav`（librosa + soundfile，`--sr 44100`）。
- 真实示例：《天下》`temp\tianxia\tianxia_origin.m4a` → `temp\tianxia\tianxia_origin.wav`；《上海滩》原曲在 `temp\shanghaitan\`。

### 3.2 UVR5 人声/伴奏分离

- 模型名 `{UVR5_MODEL}`：本机用 `HP5_only_main_vocal`（人声优先）。
- 调用方式（RVC Core API）：
  ```python
  from infer.modules.uvr5.modules import uvr
  for msg in uvr("HP5_only_main_vocal", "", vocal_dir, [Path(inp)], ins_dir, 10, "wav"):
      print(msg, flush=True)
  ```
- **输出命名规则**（重要，UVR5 固定）：
  - 输入 `{name}.wav` → 人声 `vocal_{name}.wav_10.wav`（存 `uvr5_out\vocal\`）
  - 伴奏 `instrument_{name}.wav_10.wav`（存 `uvr5_out\ins\`）
  - 真实示例：`vocal_tianxia_origin.wav_10.wav` / `instrument_tianxia_origin.wav_10.wav`。
- 分离后把 `*_10.wav` 重命名为整洁名（如 `vocal_origin.wav`、`instrumental.wav`）供下游使用。

### 3.3 RVC 变声（换声线）

- 声线模型 `{VOCAL_MODEL}`：`.pth` 文件，本机在 `E:\path\to\RVC_models\...`（《天下》用 `chuhua.pth`：`E:\path\to\RVC_models\初华\`）。
- 参数建议：
  - **男歌女唱 / 女歌男唱**：`f0_up_key` 建议 ±3 半音（《天下》初华 = **+3**）；同性别翻唱用 0。
  - `f0_method="rmvpe"`（音高提取稳）；`index_rate=0.0`（无 `.index` 文件时必须 0）；`sid=0`。
  - `filter_radius=3`、`resample_sr=0`、`rms_mix_rate=0.25`、`protect=0.33`（《天下》实测参数）。
- 调用（RVC Core API）：
  ```python
  from infer.modules.vc.modules import VC
  info = vc.get_vc("chuhua.pth")     # 加载声线
  msg, (sr, audio_opt) = vc.vc_single(0, inp, 3, "", "rmvpe", "", "", 0.0, 3, 0, 0.25, 0.33)
  ```
- **输出采样率**：RVC 输出通常 48k（`vocal_chuhua.wav`），与伴奏 44.1k 不匹配会导致混音报错 → 必须重采样 44.1k（模板已内置，用 ffmpeg `-ar 44100` 或 librosa）。

### 3.4 混音

- 用 `audio_utils.py mix`（librosa/soundfile 工具链 Python）：
  ```bash
  python audio_utils.py mix {VOCAL_CONVERTED_44K} {INSTRUMENTAL} {MIX_OUT} --vg 1.15 --ig 1.0 --peak 0.95
  ```
- 参数语义：
  - `--vg` 人声增益（vocal gain）
  - `--ig` 伴奏增益（instrumental gain）
  - `--peak` 峰值归一化目标（0.95 = -0.45dBFS，防削波）
- 真实示例（《天下》）：`--vg 1.15 --ig 1.0 --peak 0.95` → `output\tianxia_mix.wav`（221.2s，37.2MB）。
- 混音前先 `ffprobe` 校验两轨采样率一致（必须都是 44100）。

## 4. 校验清单

- [ ] 分离后有人声和伴奏两个文件（听一遍人声干净度）
- [ ] 变声输出 48k → 已重采样 44.1k
- [ ] 混音输出时长 ≈ 原曲时长，无明显削波
- [ ] 混音 wav 是后续 ASR 的输入（02），成片渲染的音频输入（03）
*（内容由AI生成，仅供参考）*
