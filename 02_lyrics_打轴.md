---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9da29870b7dfe952a0e458cf6f69e3bd_11bf164bcd2211f1afbb52540064ee0f
    ReservedCode1: fZxqbuNYSRFictB6+552w9BtuNEdBW6R0+dD7f9DCekPJLBN3rUQTxP7ugctnPvvoGlshgzwlQk+iGufgo72mmbJ+1S2oYf/sEb/m5lfd1ZSLnocAMf5T2MAg+XT0yhLwidufQKLKNPVCzFtJiiYkFDnA9jvgdfRUroNB2VxHzQmF6cy1gWz9yhtlpQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9da29870b7dfe952a0e458cf6f69e3bd_11bf164bcd2211f1afbb52540064ee0f
    ReservedCode2: fZxqbuNYSRFictB6+552w9BtuNEdBW6R0+dD7f9DCekPJLBN3rUQTxP7ugctnPvvoGlshgzwlQk+iGufgo72mmbJ+1S2oYf/sEb/m5lfd1ZSLnocAMf5T2MAg+XT0yhLwidufQKLKNPVCzFtJiiYkFDnA9jvgdfRUroNB2VxHzQmF6cy1gWz9yhtlpQ=
---

# 02 歌词打轴（ASR 词级对齐 → SRT）

> 模板脚本：`templates/asr_lyrics_template.py`（faster-whisper 词级 ASR + difflib 逐行对齐生成 SRT）。
> 真实链路参考：《天下》`temp\asr_tianxia_words.py`（词级 ASR）→ `temp\align_tianxia_srt.py`（对齐生成 `temp\tianxia_asr.srt`，44 行）；《上海滩》`temp\asr_sht.py`（段级）→ `temp\shanghaitan_asr_v2.srt`（12 句）。

## 1. 流程图

```
翻唱纯人声({VOCAL_ONLY_WAV})  ← 01 步的 vocal（变声前/后均可，建议用变声前原始人声，ASR 更准）
   │
   ▼
faster-whisper 词级 ASR（large-v3 cuda float16；无 GPU 用 small cpu int8）
   ├── word_timestamps=True
   ├── initial_prompt = 整首正确歌词全文（{LYRICS_FULL}）★ 关键
   └── 输出词级时间戳 JSON（{ASR_WORDS_JSON}）
   │
   ▼
歌词行 ↔ 词序列 顺序滑动窗口 + difflib 匹配（{LINES}：按演唱顺序含重复段的歌词行）
   │
   ▼
生成 SRT（{SRT_OUT}）+ 对齐校验 JSON（每行匹配得分，供人工核对）
```

## 2. 为什么必须"词级 ASR + 整首歌词作 initial_prompt"

- **词级时间戳**（`word_timestamps=True`）是逐句打轴的原料；只有段级时间戳时无法精确切到每个字。
- **initial_prompt 传整首正确歌词**（含重复段）可大幅压低 ASR 错字率（人名、古风词、粤语词尤甚），保证"字幕即原词"。
- 翻唱人声（换声线后）音色与训练语料差异大时，**优先用变声前的原始人声做 ASR**，识别率更高；时间轴同样适用成片（混音未变速）。

## 3. 步骤详解

### 3.1 准备输入

- 输入音频：`{VOCAL_ONLY_WAV}`（纯人声，44.1k wav）。
- 歌词文本：`{LYRICS_FULL}` 与演唱顺序行 `{LINES}`。
  - `{LYRICS_FULL}`：整首歌词全文（不重复段即可），作为 initial_prompt。
  - `{LINES}`：**按演唱顺序逐行**（重复段照给），如《天下》44 行含 3 段副歌 + 尾声重复 + 末段主歌重唱。

### 3.2 运行词级 ASR

- 模型与设备：
  - GPU：`WhisperModel("large-v3", device="cuda", compute_type="float16")`
  - CPU：`WhisperModel("small", device="cpu", compute_type="int8")`（慢但可用）
- 关键参数：`language="zh"`、`beam_size=5`、`vad_filter=True`、`word_timestamps=True`、`initial_prompt={LYRICS_FULL}`。
- 塌缩段时间轴修复：ASR 个别段塌缩（无声/异常段），可**对局部区间复跑**（`asr_tianxia_rerun.py` 模式：切 `vocal_115_170.wav` 段，段内时间 + 偏移还原）。
- 输出：词序列 JSON `[{word, start, end, prob}, ...]`。

### 3.3 歌词行 ↔ 词时间戳对齐

- 核心算法（`align_tianxia_srt.py`）：
  1. 顺序指针 `p=0`；对每行歌词，在 `p..p+10` 内枚举窗口起点、长度 = 行字符数 ± 3~7；
  2. 用 `difflib.SequenceMatcher.ratio()` 求与窗口拼接文本的最佳匹配；
  3. 行时间 = 窗口首词 `start` ～ 末词 `end`；`p = j1` 继续下一行。
- **重复段按演唱顺序给足**（同一句歌词出现几次就给几行，如《天下》44 行）。
- **间奏留白**：两行之间的空隙不分配歌词行，自然留白。
- 输出 SRT 时间格式：`HH:MM:SS,mmm`；同时输出 `align_check.json` 记录每行 `score`/`asr` 片段，**人工抽查低分行**（score < 0.7 建议核对）。

### 3.4 SRT 格式要求（渲染脚本直接消费）

```
1
00:00:27,890 --> 00:00:32,710
烽烟起 寻爱似浪淘沙
2
00:00:33,010 --> 00:00:39,330
遇见她 如春水映梨花
...
```
- 每行一句完整歌词，时间严格递增、允许相邻行首尾相接（下一行 start = 上一行 end）。

## 4. 真实示例

| 项 | 《上海滩》 | 《天下》 |
|---|---|---|
| ASR 输入 | `temp\uvr5_out\vocal\vocal_shanghaitan_origin.wav_10.wav` | `temp\tianxia\vocal_origin.wav`（另对 115–170s 复跑过 `vocal_115_170.wav`） |
| 模型 | large-v3 cuda float16 | large-v3 cuda float16 |
| initial_prompt | 粤语歌词 | 《天下》全词 |
| SRT | `temp\shanghaitan_asr_v2.srt`（12 句，16.30s 起） | `temp\tianxia_asr.srt`（44 行，27.89s–213.78s） |
| 结构 | 主歌×4 + 副歌×4（×2 段） | 主歌1(4)+副歌1(14)+间奏+副歌2(14)+副歌3(8)+尾声(4) |

## 5. 校验清单

- [ ] 每行时间与演唱起始吻合（抽查开头/副歌/结尾）
- [ ] 重复段都有对应行（行数 = 演唱次数）
- [ ] 行间无重叠，SRT 时间递增
- [ ] 渲染前用播放器或 ffmpeg 快速过一遍时间轴（`ffplay -sub_charenc UTF-8`）
*（内容由AI生成，仅供参考）*
