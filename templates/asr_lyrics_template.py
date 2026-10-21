# -*- coding: utf-8 -*-
"""asr_lyrics_template.py — 歌词打轴模板（词级 ASR + 逐行对齐生成 SRT）

流程：faster-whisper 词级 ASR（initial_prompt=整首正确歌词）
      → 词级时间戳 JSON
      → 歌词行（按演唱顺序）↔ 词序列 difflib 滑动窗口对齐
      → 逐句 SRT（重复段按演唱顺序给足、间奏留白）+ 对齐校验 JSON

用法：
  python asr_lyrics_template.py asr        # 只跑 ASR，输出 asr_words.json
  python asr_lyrics_template.py align      # 只跑对齐，输出 SRT
  python asr_lyrics_template.py            # 全流程

所有路径为占位符 {XXX}；真实示例：《天下》temp\tianxia\ 下 asr_words.json /
asr_segments.json → tianxia_asr.srt（44 行，27.89s–213.78s）。
参考脚本：temp\asr_tianxia_words.py（ASR）、temp\align_tianxia_srt.py（对齐）。
"""
import difflib
import io
import json
import os
import sys

# ==================== CONFIG ====================
TEMP = r"{TEMP_DIR}"                          # 例: C:\path\to\temp
WORK_DIR = os.path.join(TEMP, "{SONG_ID}")    # 例: tianxia
VOCAL_ONLY_WAV = r"{VOCAL_ONLY_WAV}"          # 例: temp\tianxia\vocal_origin.wav（用变声前原始人声，识别更准）
SRT_OUT = os.path.join(WORK_DIR, "{SRT_OUT}") # 例: tianxia_asr.srt
WORDS_JSON = os.path.join(WORK_DIR, "asr_words.json")
SEGS_JSON = os.path.join(WORK_DIR, "asr_segments.json")
ALIGN_CHECK_JSON = os.path.join(WORK_DIR, "align_check.json")

# 模型与设备：GPU 用 large-v3/cuda/float16；CPU 用 small/cpu/int8
WHISPER_MODEL = "{WHISPER_MODEL}"   # 例: large-v3 / small
WHISPER_DEVICE = "cuda"             # cpu 兜底
WHISPER_TYPE = "float16"            # cpu 用 int8

# 整首正确歌词（含重复段，ASR 用 initial_prompt 压错字）：
LYRICS_FULL = "{LYRICS_FULL}"

# 歌词行（按演唱顺序，含重复段）——对齐基准；行数 = 演唱次数
LINES = [
    "{LINE_1}",
    # ... 按演唱顺序补全，重复段照给（例：副歌唱 3 遍就给 3 组相同文本行）
]
# ==================== CONFIG 结束 ====================

# HF 镜像 + torch dll（见 04 踩坑清单）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ["PATH"] = r"{TORCH_LIB}" + ";" + os.environ.get("PATH", "")  # 例: E:\...\torch\lib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def run_asr():
    from faster_whisper import WhisperModel
    print("loading model...", flush=True)
    model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_TYPE)
    segments, info = model.transcribe(
        VOCAL_ONLY_WAV, language="zh", beam_size=5, vad_filter=True,
        word_timestamps=True, initial_prompt=LYRICS_FULL,
    )
    words_all, segs_all = [], []
    for seg in segments:
        segs_all.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})
        for w in (seg.words or []):
            words_all.append({
                "word": w.word.strip(), "start": w.start, "end": w.end,
                "prob": float(w.probability),
            })
    with open(WORDS_JSON, "w", encoding="utf-8") as f:
        json.dump(words_all, f, ensure_ascii=False, indent=1)
    with open(SEGS_JSON, "w", encoding="utf-8") as f:
        json.dump(segs_all, f, ensure_ascii=False, indent=1)
    print("ASR_DONE words=", len(words_all), "segs=", len(segs_all))


def _fmt_ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); ms = int(round((t - int(t)) * 1000))
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def align_to_srt():
    """歌词行 ↔ 词序列滑动窗口 difflib 对齐（参考 align_tianxia_srt.py）"""
    with open(WORDS_JSON, encoding="utf-8") as f:
        words = json.load(f)
    text_all = "".join(w["word"] for w in words)
    line_starts = []  # 记录每行在 text_all 中的字符起点（可容忍空/标点误差）
    p = 0
    for line in LINES:
        # 滑动窗口：在 p 后 ±10 词内找与 line 相似度最高的连续窗口
        best = (0.0, 0, 0)
        for j0 in range(max(0, p - 10), min(len(words), p + 10)):
            for j1 in range(j0 + 1, min(len(words), j0 + len(line) + 8)):
                seg = "".join(w["word"] for w in words[j0:j1])
                score = difflib.SequenceMatcher(None, line, seg).ratio()
                if score > best[0]:
                    best = (score, j0, j1)
        _, j0, j1 = best
        line_starts.append((p, j0, j1))
        p = j1

    # 生成 SRT：行时间 = 窗口首词 start ~ 末词 end
    srt_lines, check = [], []
    for idx, (line, (_, j0, j1)) in enumerate(zip(LINES, line_starts), 1):
        if j0 >= len(words) or j1 <= j0:
            continue
        start, end = words[j0]["start"], words[j1 - 1]["end"]
        asr_text = "".join(w["word"] for w in words[j0:j1])
        srt_lines.append("%d\n%s --> %s\n%s\n" % (idx, _fmt_ts(start), _fmt_ts(end), line))
        check.append({"idx": idx, "line": line, "asr": asr_text,
                      "start": start, "end": end,
                      "score": difflib.SequenceMatcher(None, line, asr_text).ratio()})
    with open(SRT_OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_lines))
    with open(ALIGN_CHECK_JSON, "w", encoding="utf-8") as f:
        json.dump(check, f, ensure_ascii=False, indent=1)
    print("SRT_DONE lines=", len(srt_lines), "->", SRT_OUT)
    print("注意：score<0.7 的行请人工核对（见 align_check.json）")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("asr", "all"):
        run_asr()
    if cmd in ("align", "all"):
        align_to_srt()


if __name__ == "__main__":
    main()
