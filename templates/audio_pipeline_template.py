# -*- coding: utf-8 -*-
"""audio_pipeline_template.py — AI 翻唱音频制作一体化模板

流程：原曲转 wav → UVR5 人声/伴奏分离 → RVC 变声 → 44.1k 重采样 → 混音 → 翻唱音频.wav

用法：
  python audio_pipeline_template.py             # 全流程执行（步骤开关在 CONFIG）
  python audio_pipeline_template.py --mix-only  # 只做混音（分离/变声已完成）

所有路径均为占位符 {XXX}，替换为你的实际路径；
下方每处附《天下》《上海滩》真实示例值（示例行以 # 例: 开头）。

前置环境（见 01_audio_制作音频.md / 04_gotchas 踩坑清单）：
- RVC Core 目录（含 UVR5 + RVC 模块）
- 本机工具链 Python（librosa + soundfile，用于 to_wav/mix，见 audio_utils.py）
- 若缺 cublas64_12.dll：脚本已自动把 torch\lib 前置到 PATH
"""
import os
import subprocess
import sys

# ==================== CONFIG（全部占位符，替换成实际值） ====================
# --- 通用 ---
TEMP = r"{TEMP_DIR}"                    # 例: C:\path\to\temp
WORK_DIR = os.path.join(TEMP, "{SONG_ID}")   # 例: tianxia / shanghaitan（每首歌一个子目录）
OUTPUT_DIR = r"{OUTPUT_DIR}"            # 例: C:\path\to\output

# --- 1. 原曲 ---
ORIGINAL_AUDIO = r"{ORIGINAL_AUDIO}"    # 例: temp\tianxia\tianxia_origin.m4a
ORIGINAL_WAV = os.path.join(WORK_DIR, "{ORIGINAL_WAV}")   # 例: tianxia_origin.wav

# --- 2. UVR5 ---
RVC_CORE = r"{RVC_CORE}"                # 例: E:\path\to\RVC_Core
TORCH_LIB = r"{TORCH_LIB}"              # 例: E:\path\to\torch\lib
UVR5_MODEL = "{UVR5_MODEL}"             # 例: HP5_only_main_vocal
UVR5_VOCAL_DIR = os.path.join(WORK_DIR, "uvr5_out", "vocal")   # 分离后人声输出目录
UVR5_INS_DIR = os.path.join(WORK_DIR, "uvr5_out", "ins")       # 分离后伴奏输出目录
VOCAL_ORIGIN = os.path.join(WORK_DIR, "vocal_origin.wav")      # 重命名后的原始人声
INSTRUMENTAL = os.path.join(WORK_DIR, "instrumental.wav")      # 重命名后的伴奏

# --- 3. RVC ---
VOCAL_MODEL = "{VOCAL_MODEL}"           # 例: chuhua.pth（初华声线）
F0_UP_KEY = {F0_UP_KEY}                 # 例: 3（男歌女唱升 3 半音；同性别 0）
F0_METHOD = "rmvpe"
INDEX_RATE = 0.0                        # 无 .index 文件必须 0
VOCAL_CONVERTED = os.path.join(WORK_DIR, "vocal_chuhua.wav")   # RVC 输出（48k）
VOCAL_CONVERTED_44K = os.path.join(WORK_DIR, "vocal_chuhua_44k.wav")  # 重采样 44.1k

# --- 4. 混音 ---
MIX_OUT = os.path.join(OUTPUT_DIR, "{MIX_OUT}")   # 例: tianxia_mix.wav
VOCAL_GAIN = {VOCAL_GAIN}               # 例: 1.15
INST_GAIN = {INST_GAIN}                 # 例: 1.0
PEAK = {PEAK}                           # 例: 0.95

# --- 步骤开关 ---
DO_TO_WAV = True
DO_UVR5 = True
DO_RVC = True
DO_RESAMPLE_44K = True
DO_MIX = True
# ==================== CONFIG 结束 ====================

# 混音工具（本机工具链 Python + librosa + soundfile；audio_utils.py 见 temp\cover_app\）
AUDIO_UTILS_PY = r"{AUDIO_UTILS_PY}"    # 例: temp\cover_app\audio_utils.py
TOOL_PYTHON = r"{TOOL_PYTHON}"          # 例: C:\path\to\toolchain\python.exe

FFMPEG = r"{FFMPEG}"                    # 例: C:\path\to\ffmpeg.exe


def _uvr5_env():
    env = dict(os.environ)
    env["PATH"] = RVC_CORE + os.pathsep + env.get("PATH", "")
    return env


def to_wav():
    """ffmpeg 或 librosa 转 44.1k 立体声 wav"""
    os.makedirs(os.path.dirname(ORIGINAL_WAV), exist_ok=True)
    if not os.path.exists(ORIGINAL_WAV):
        subprocess.run([
            FFMPEG, "-y", "-i", ORIGINAL_AUDIO,
            "-ar", "44100", "-ac", "2", ORIGINAL_WAV,
        ], check=True)
        print("TO_WAV_OK", ORIGINAL_WAV)


def uvr5_separate():
    """UVR5 人声/伴奏分离（RVC Core 内 API）"""
    import sys as _sys
    core = RVC_CORE
    _sys.path.insert(0, core)
    env = _uvr5_env()
    code = r'''
import os, sys
core = r"{CORE}"
os.chdir(core); sys.path.insert(0, core)
os.environ["PATH"] = core + os.pathsep + os.environ.get("PATH", "")
from dotenv import load_dotenv
load_dotenv(os.path.join(core, ".env"))
from configs.config import Config
from infer.modules.uvr5.modules import uvr
from pathlib import Path
vocal_dir = r"{VOCAL_DIR}"; ins_dir = r"{INS_DIR}"
os.makedirs(vocal_dir, exist_ok=True); os.makedirs(ins_dir, exist_ok=True)
for msg in uvr(r"{MODEL}", "", vocal_dir, [Path(r"{WAV}")], ins_dir, 10, "wav"):
    print(msg, flush=True)
print("SEP_DONE")
'''.format(CORE=core, VOCAL_DIR=UVR5_VOCAL_DIR, INS_DIR=UVR5_INS_DIR,
           MODEL=UVR5_MODEL, WAV=ORIGINAL_WAV)
    subprocess.run([TOOL_PYTHON, "-c", code], check=True, env=env)
    # 重命名 UVR5 固定命名（vocal_{name}.wav_10.wav）为整洁名
    import glob
    v = glob.glob(os.path.join(UVR5_VOCAL_DIR, "vocal_*.wav_10.wav"))
    i = glob.glob(os.path.join(UVR5_INS_DIR, "instrument_*.wav_10.wav"))
    if v:
        os.replace(v[0], VOCAL_ORIGIN)
    if i:
        os.replace(i[0], INSTRUMENTAL)
    print("UVR5_RENAMED", VOCAL_ORIGIN, INSTRUMENTAL)


def rvc_convert():
    """RVC 变声（RVC Core 内 API）"""
    core = RVC_CORE
    env = dict(os.environ)
    env["PATH"] = core + os.pathsep + TORCH_LIB + os.pathsep + env.get("PATH", "")
    code = r'''
import os, sys
core = r"{CORE}"; torchlib = r"{TORCH_LIB}"
os.chdir(core); sys.path.insert(0, core)
os.environ["PATH"] = core + os.pathsep + torchlib + os.pathsep + os.environ.get("PATH", "")
from dotenv import load_dotenv
load_dotenv(os.path.join(core, ".env"))
from configs.config import Config
from infer.modules.vc.modules import VC
from scipy.io import wavfile
cfg = Config(); vc = VC(cfg)
info = vc.get_vc(r"{MODEL}")
print("GETVC:", info, flush=True)
msg, (sr, audio_opt) = vc.vc_single(0, r"{IN}", {F0}, "", r"{F0M}", "", "", {IR}, 3, 0, 0.25, 0.33)
print("INFO:", msg, flush=True)
if audio_opt is not None:
    wavfile.write(r"{OUT}", sr, audio_opt)
    print("SAVED:", r"{OUT}", "sr=", sr, flush=True)
print("RVC_DONE")
'''.format(CORE=core, TORCH_LIB=TORCH_LIB, MODEL=VOCAL_MODEL, IN=VOCAL_ORIGIN,
           F0=F0_UP_KEY, F0M=F0_METHOD, IR=INDEX_RATE, OUT=VOCAL_CONVERTED)
    subprocess.run([TOOL_PYTHON, "-c", code], check=True, env=env)


def resample_44k():
    """RVC 输出 48k → 44.1k（混音前必须）"""
    subprocess.run([
        FFMPEG, "-y", "-i", VOCAL_CONVERTED,
        "-ar", "44100", "-ac", "2", VOCAL_CONVERTED_44K,
    ], check=True)
    print("RESAMPLE_OK", VOCAL_CONVERTED_44K)


def mix():
    """人声 + 伴奏混音（librosa/soundfile 工具链）"""
    subprocess.run([
        TOOL_PYTHON, AUDIO_UTILS_PY, "mix",
        VOCAL_CONVERTED_44K, INSTRUMENTAL, MIX_OUT,
        "--vg", str(VOCAL_GAIN), "--ig", str(INST_GAIN), "--peak", str(PEAK),
    ], check=True)
    print("MIX_OK", MIX_OUT)


def main():
    if DO_TO_WAV:
        to_wav()
    if DO_UVR5:
        uvr5_separate()
    if DO_RVC:
        rvc_convert()
    if DO_RESAMPLE_44K:
        resample_44k()
    if DO_MIX:
        mix()
    print("PIPELINE_DONE", MIX_OUT)


if __name__ == "__main__":
    main()
