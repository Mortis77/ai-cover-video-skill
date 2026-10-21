# -*- coding: utf-8 -*-
"""render_ktv_template.py — KTV 五行同屏滚动歌词成片渲染模板（参数化）

功能：
  - 背景图 cover 铺满（4:3/16:9 均支持，保人物全宽）
  - KTV 五行同屏滚动：行1/2 已唱灰、行3 当前金、行4/5 未唱暗灰；行距 138px；
    当前句固定行3；切换 0.5s 上移顶行滚出；已唱层用句结束触发；未唱层首句特例
  - 歌名横排（天下式）/ 竖排（上海滩式）二选一
  - 渲染：短歌单段（全局 Q 表达式）；长歌自动分段渲染 + concat（规避命令行超限）

用法：
  python render_ktv_template.py             # 全流程渲染
  python render_ktv_template.py --dry-run   # 只打印将执行的 ffmpeg 命令不执行

所有路径为占位符 {XXX}；真实示例值见注释。
参考脚本：temp\render_sht_gen8.py（右对齐+竖排歌名+单段）、
          temp\render_tianxia_v2.py（居中偏右+横排歌名+分段 concat）。
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ==================== CONFIG（全部占位符） ====================
TEMP_DIR = r"{TEMP_DIR}"                    # 例: C:\path\to\temp
OUTPUT_DIR = r"{OUTPUT_DIR}"                # 例: C:\path\to\output
FFMPEG = r"{FFMPEG}"                        # 例: C:\path\to\ffmpeg.exe
FONT = "simkai.ttf"                         # 相对路径（cwd=TEMP_DIR 生效，见 04 坑 3）

# --- 输入素材 ---
BG_IMAGE = r"{BG_IMAGE}"                    # 例: C:\path\to\bg_image_2.jpg
AUDIO = r"{AUDIO}"                          # 例: output\tianxia_mix.wav（01 步产出）
SRT_IN = r"{SRT_IN}"                        # 例: temp\tianxia_asr.srt（02 步产出）
OUTPUT_MP4 = os.path.join(OUTPUT_DIR, "{OUTPUT_MP4}")   # 例: tianxia_final.mp4

# --- 歌名 ---
TITLE = "{TITLE}"                           # 例: 天下 / 上海灘
TITLE_MODE = "horizontal"                   # "horizontal"横排(天下) / "vertical"竖排(上海滩)
TITLE_FONT_SIZE = 64                        # 天下=64 / 上海滩=100
TITLE_X_EXPR = "(w-text_w)/2+340"           # 横排基准（天下）；上海滩竖排固定 x=430
TITLE_X_FIXED = 430                         # 竖排歌名固定 x（上海滩）
TITLE_Y = 120                               # 横排 y；竖排 y0=300
TITLE_STEP = 132                            # 竖排字距（上海滩）

# --- 布局 ---
ALIGN_X_EXPR = "(w-text_w)/2+340"           # 歌词 x 基准：天下居中偏右 / 上海滩右对齐 'w-text_w-60'
LINE_Y_CURRENT = 516                        # 当前句（行3）y 顶
LINE_SPACING = 138                          # 行距
FONT_SIZE = 48
COLOR_SUNG = "0x8A8A8A"                     # 已唱灰
COLOR_CURRENT = "0xFFDD88"                  # 当前金
COLOR_NEXT = "0x555555"                     # 未唱暗灰
ALPHA_SUNG = "0.55"                         # 已唱/未唱文字透明度（写在 fontcolor 后 @ 或 alpha 中）
ROLL = 0.5                                  # 切换动画秒数

# --- 渲染模式 ---
# "single"    单段：全局 Q 表达式（句数 < ~15 可用）
# "segmented" 分段：自动按句切段渲染 + concat（长歌推荐，默认）
RENDER_MODE = "segmented"
MAX_SENT_PER_SEG = 20                        # segmented 模式下每段最大句数（控制命令长度 <30000）
# 手动段边界（秒），留空则按 MAX_SENT_PER_SEG 自动切；例: [(0.0,92.8),(92.8,159.4),(159.4,186.12),(186.12,221.2)]
SEGS = []
# ==================== CONFIG 结束 ====================


def parse_srt(path):
    """解析 SRT → [(start, end, text), ...]（start/end 秒）。
    兼容块内首行为序号或时间行的两种形态。"""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    blocks = re.split(r"\n\s*\n", raw.strip())
    out = []
    ts_re = re.compile(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
    for b in blocks:
        lines = [x.strip() for x in b.splitlines() if x.strip()]
        if len(lines) < 2:
            continue
        m = None
        time_idx = 0
        for k, ln in enumerate(lines):
            if ts_re.search(ln):
                m = ts_re.search(ln); time_idx = k; break
        if not m:
            continue
        def to_s(g):
            return int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000.0
        start = to_s(m.groups()[:4]); end = to_s(m.groups()[4:])
        text = " ".join(lines[time_idx + 1:])
        out.append((start, end, text))
    return out


def fmt_ts(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); ms = int(round((t - int(t)) * 1000))
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def write_textfiles(lines):
    """每句歌词一个 textfile（UTF-8），返回 {idx: 文件名相对路径}；必须相对路径 + cwd=TEMP"""
    d = os.path.join(TEMP_DIR, "ktv_lines")
    os.makedirs(d, exist_ok=True)
    files = {}
    for i, (_, _, text) in enumerate(lines):
        name = "line_%03d.txt" % i
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(text)
        files[i] = name  # 相对路径
    return files


def title_drawtexts():
    """歌名 drawtext 段（横排/竖排）。竖排逐字：x 固定、y 递增"""
    if TITLE_MODE == "vertical":
        parts = []
        for ci, ch in enumerate(TITLE):
            parts.append(
                "drawtext=fontfile=%s:textfile=title_%d.txt:fontsize=%d:fontcolor=%s:"
                "borderw=2:bordercolor=white:x=%d:y=%d:alpha='clip(t*3,0,1)'"
                % (FONT, ci, TITLE_FONT_SIZE, COLOR_CURRENT, TITLE_X_FIXED,
                   TITLE_Y + ci * TITLE_STEP)
            )
        return ",".join(parts)
    return (
        "drawtext=fontfile=%s:textfile=title.txt:fontsize=%d:fontcolor=%s:"
        "borderw=2:bordercolor=white:x='%s':y=%d:alpha='clip(t*3,0,1)'"
        % (FONT, TITLE_FONT_SIZE, COLOR_CURRENT, TITLE_X_EXPR, TITLE_Y)
    )


def bg_filter():
    """背景 cover 铺满：4:3/竖图保人物全宽仅裁上下；16:9 直接缩放"""
    return "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p"


def line_expr_single(i, lines, audio_end):
    """方案 A（单段）：全局 Q 表达式。y = 516 + (i-3)*138 - 138*Q(t)，Q=-4+Σclip((t-s_k)/ROLL)"""
    s = [x[0] for x in lines]
    n = len(s)
    q = ["-4"]
    for k in range(n):
        q.append("clip((t-%s)/%s,0,1)" % (fmt_sec(s[k] - 0.0), ROLL))
    q_expr = "+".join(q)
    y = "%s+(%d)*%s-138*(%s)" % (LINE_Y_CURRENT, i - 3, LINE_SPACING, q_expr)
    # alpha：当前句=金，已唱/未唱按颜色透明度走（颜色已含透明度见 drawtext）
    return y


def fmt_sec(t):
    return "%.3f" % t


def layer_exprs_seg(i, lines, audio_end, t0):
    """方案 B（分段）：句 i 的 5 层表达式（已唱2 + 当前1 + 未唱2）。
    返回 [(kind, y_expr, alpha_expr, color, alpha)], kind in sung/current/next。
    所有时间戳为段内相对时间（global - t0）。参考 render_tianxia_v2.py。"""
    s = [x[0] for x in lines]
    e = [x[1] for x in lines]
    n = len(lines)
    ss = lambda g: fmt_sec(s[g] - t0)   # 句 start（段内）
    ee = lambda g: fmt_sec(e[g] - t0)   # 句 end（段内）
    end_t = fmt_sec(audio_end - t0)
    layers = []

    # 已唱层（行2 y=378 → 行1 y=240 → 滚出）：句 i 显示期 [s_{i+1}, e_{i+2}]；
    # 淡入由下一句开始 s_{i+1} 触发（否则会与当前层重复显示）；
    # y 用句结束触发上移：e_{i+1} 触发→行1，e_{i+2} 触发→滚出（y 继续上移淡出）
    if i >= 0:
        y_sung = "%s-138*(clip((t-%s)/%s,0,1)+clip((t-%s)/%s,0,1))" % (
            LINE_Y_CURRENT - LINE_SPACING, ee(i + 1) if i + 1 < n else end_t, ROLL,
            ee(i + 2) if i + 2 < n else end_t, ROLL)
        a_sung = "clip((t-%s)*4,0,1)*clip((%s-t)*4,0,1)" % (
            ss(i + 1) if i + 1 < n else end_t, ee(i + 2) if i + 2 < n else end_t)
        layers.append(("sung", y_sung, a_sung))

    # 当前层（行3 固定 y=516）
    a_cur = "clip((t-%s)*4,0,1)*clip((%s-t)*4,0,1)" % (ss(i), ss(i + 1) if i + 1 < n else end_t)
    layers.append(("current", str(LINE_Y_CURRENT), a_cur))

    # 未唱层（行5 y=792 → 行4 y=654）：句 i 显示期 [s_{i-1}, s_i]；首句特例 i=0 不生成
    if i >= 1:
        y_next = "%s-138*clip((t-%s)/%s,0,1)" % (LINE_Y_CURRENT + 2 * LINE_SPACING, ss(i - 1), ROLL)
        a_next = "clip((t-%s)*2,0,1)*clip((%s-t)*4,0,1)" % (ss(i - 1), ss(i))
        layers.append(("next", y_next, a_next))
    return layers


def drawtext_of(layer):
    kind, y, a = layer
    color = {"sung": COLOR_SUNG, "current": COLOR_CURRENT, "next": COLOR_NEXT}[kind]
    alpha = {"sung": ALPHA_SUNG, "current": "1.0", "next": "0.5"}[kind]
    # 颜色透明度直接拼在 fontcolor 后（fontcolor=0xRRGGBB@AA），alpha 表达式另用 alpha= 控制淡入淡出
    return ("drawtext=fontfile=%s:textfile=%%s:fontsize=%d:fontcolor=%s@%s:borderw=%d:"
            "bordercolor=white:x='%s':y='%s':alpha='%s'" % (
                FONT, FONT_SIZE, color, alpha,
                2 if kind == "current" else 1,
                ALIGN_X_EXPR, y, a))


def build_segment_cmd(lines, files, t0, t1, seg_idx):
    """构造某段的 ffmpeg 命令（段内时间从 0 起）"""
    dur = t1 - t0
    end_t = t1
    filters = [bg_filter()]
    # 歌名层（每段都加，drawtext 前先写 title.txt / title_0.txt...）
    filters.append(title_drawtexts())
    # 五行层：只保留显示期与 [t0,t1] 相交的句
    for i, (s, e, _) in enumerate(lines):
        if e < t0 or s > t1:      # 本段完全不包含该句 → 跳过（跨段句两段都渲染）
            continue
        for layer in layer_exprs_seg(i, lines, end_t, t0):
            dt = drawtext_of(layer) % files[i]
            filters.append(dt)
    filtergraph = ",".join(filters) + "[v]"
    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-t", fmt_sec(dur), "-i", BG_IMAGE,
        "-ss", fmt_sec(t0), "-t", fmt_sec(dur), "-i", AUDIO,
        "-filter_complex", filtergraph,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-crf", "19", "-preset", "slow",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        os.path.join(TEMP_DIR, "seg_%d.mp4" % seg_idx),
    ]
    return cmd


def auto_segs(lines, mode):
    if mode == "single":
        return [(0.0, lines[-1][1] if lines else 0.0)]
    if SEGS:
        return SEGS
    # 按句 start 切段：每段最多 MAX_SENT_PER_SEG 句，段边界=下一段首句 start
    cuts = []
    for idx in range(0, len(lines), MAX_SENT_PER_SEG):
        cuts.append(lines[idx][0])
    cuts.append(lines[-1][1])
    return list(zip(cuts[:-1], cuts[1:]))


def main():
    dry = "--dry-run" in sys.argv
    lines = parse_srt(SRT_IN)
    if not lines:
        print("NO_LINES"); return 1
    audio_end = lines[-1][1]
    files = write_textfiles(lines)

    # 歌名 textfile（title.txt 横排 / title_%d.txt 竖排逐字）
    if TITLE_MODE == "vertical":
        for ci, ch in enumerate(TITLE):
            with open(os.path.join(TEMP_DIR, "title_%d.txt" % ci), "w", encoding="utf-8") as f:
                f.write(ch)
    else:
        with open(os.path.join(TEMP_DIR, "title.txt"), "w", encoding="utf-8") as f:
            f.write(TITLE)

    # 备份旧输出
    if os.path.exists(OUTPUT_MP4):
        bak = OUTPUT_MP4 + "_backup.mp4"
        shutil.copy2(OUTPUT_MP4, bak)
        print("BACKUP", bak)

    segs = auto_segs(lines, RENDER_MODE)
    seg_files = []
    for idx, (t0, t1) in enumerate(segs):
        cmd = build_segment_cmd(lines, files, t0, t1, idx)
        if dry:
            print("CMD_SEG%d len=%d\n%s\n" % (idx, len(" ".join(cmd)), " ".join(cmd)))
            continue
        print("RENDER_SEG%d [%s,%s]" % (idx, fmt_sec(t0), fmt_sec(t1)))
        subprocess.run(cmd, cwd=TEMP_DIR, check=True)   # cwd=TEMP：fontfile/textfile 相对路径
        seg_files.append(os.path.join(TEMP_DIR, "seg_%d.mp4" % idx))

    if dry or not seg_files:
        return 0

    # concat 合并
    n = len(seg_files)
    inputs, cfilter = [], []
    for i in range(n):
        inputs += ["-i", seg_files[i]]
        cfilter += ["[%d:v]" % i, "[%d:a]" % i]
    cfilter = "".join(cfilter) + "concat=n=%d:v=1:a=1[v][a]" % n
    cmd = [
        FFMPEG, "-y", *inputs, "-filter_complex", cfilter,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-crf", "19", "-preset", "slow",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        OUTPUT_MP4,
    ]
    subprocess.run(cmd, cwd=TEMP_DIR, check=True)
    print("DONE", OUTPUT_MP4)


if __name__ == "__main__":
    main()
