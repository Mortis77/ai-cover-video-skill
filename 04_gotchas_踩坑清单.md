---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9da29870b7dfe952a0e458cf6f69e3bd_168cd2bfcd2211f1b76f525400638852
    ReservedCode1: f4iwMRBuixAN1JE5NJz7OhkK2ffEaRCaekPwXbZifjZ2t3wt8WBCyW02M+oik9VZUOBcHt8P76VKLWqMBNuIHyPVjap85MRbAcjRixUQJCMxAUon6TvRmDocrzBrFcMNjjyAKwTpOjRMWWSGN/Z5pxcFpsFO3cfxzRRiqYh9yoFuGQrVd7GE1+KxgjY=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9da29870b7dfe952a0e458cf6f69e3bd_168cd2bfcd2211f1b76f525400638852
    ReservedCode2: f4iwMRBuixAN1JE5NJz7OhkK2ffEaRCaekPwXbZifjZ2t3wt8WBCyW02M+oik9VZUOBcHt8P76VKLWqMBNuIHyPVjap85MRbAcjRixUQJCMxAUon6TvRmDocrzBrFcMNjjyAKwTpOjRMWWSGN/Z5pxcFpsFO3cfxzRRiqYh9yoFuGQrVd7GE1+KxgjY=
---

# 04 踩坑清单（本机已验证全部坑位）

> 每条均为本机实际踩过并验证的结论；新环境先探测再执行。

## A. ffmpeg（vision-bridge 构建限制）

1. **无 `-filter_complex_script`，也不支持 filter 文件语法**（`/filter_complex` 等皆不支持）。超长 filtergraph 只能：内联 `-filter_complex` 或分段渲染+concat。探测命令：
   ```bash
   ffmpeg -h filter_complex_script 2>&1 | findstr /i "unrecognized"
   ```
   输出含 `Unrecognized option` 即不支持。

2. **`drawtext` 的 `text=` 内联含空格/引号会报错**。歌词含空格（如粤语/英文）时必然触发 → **一律用 `textfile=相对路径.txt`**。

3. **`fontfile` / `textfile` 必须相对路径 + 进程 `cwd=TEMP`**（vision-bridge 构建的解析器只接受相对路径）。脚本里：
   ```python
   subprocess.run(cmd, cwd=temp_dir)   # fontfile=simkai.ttf 等相对路径
   ```

4. **`drawtext` 的 `y` 与 `text` 求值引擎分离**：`y='基准 - 偏移*共享变量'`（把变量在 y 中复用）在本机构建会得到奇怪结果。**把共享变量直接展开成字面 clip 表达式**（参考 03 方案 B：每层 y 写死自己的窗口项）。

5. **单条 filter_complex 过长**：>30000 字符 / 超过 Windows 命令行 32767 字符硬限会直接失败（`CreateProcess` 报错或 ffmpeg 卡死）。**长歌必须分段渲染 + concat**（每段只含本段显示期相交的层，段内相对时间）。判断标准：`len(cmd) > 30000` 就分。

6. **背景 cover 铺满**：4:3/竖图直接 `scale=1920:1080` 会横向拉伸人物变形；用 `scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080`（放大到宽 1920、高 1440，再裁高 1080，保留人物全宽仅裁上下）。

7. **编码参数**：`-c:v libx264 -crf 19 -preset slow -pix_fmt yuv420p -c:a aac -b:a 192k`；分段与 concat 必须同参数，否则拼接花屏。

## B. RVC / UVR5 环境

8. **缺 `cublas64_12.dll`**：直接 import torch 相关模块会 `ImportError`。解决：`PATH` 前置 `E:\path\to\torch\lib`。RVC Core 脚本头部固定加上（见 01 模板）。

9. **HF 镜像三件套**（faster-whisper 下模型用）：
   ```
   HF_ENDPOINT=https://hf-mirror.com
   HF_HUB_DISABLE_XET=1
   HF_HUB_DISABLE_TELEMETRY=1
   ```
   不设会卡在下载 huggingface.co。

10. **UVR5 输出命名规则**：输入 `{name}.wav` → 人声 `vocal_{name}.wav_10.wav`、伴奏 `instrument_{name}.wav_10.wav`（`_10` 为 UVR5 固定后缀）；分别落在 `uvr5_out\vocal\` 与 `uvr5_out\ins\`。**别找错文件名**，分离后建议重命名成整洁名。

11. **UVR5 模型名用 `HP5_only_main_vocal`**（人声优先，实测分离干净）。模型路径在 RVC Core 内（`assets/uvr5_weights/`），脚本里只传模型名。

12. **RVC 模型 `.pth` 路径**：《天下》用 `E:\path\to\RVC_models\chuhua.pth`。**无 `.index` 文件时 `index_rate` 必须传 0.0**，否则报错。`vc.get_vc("chuhua.pth")` 只认文件名，`.pth` 需在 RVC 默认模型目录或带路径复制。

13. **RVC 输出 48k**：`vc_single` 返回 `sr` 通常 48000；伴奏是 44100 → **必须先重采样 44.1k 再混音**，否则 `sample rate mismatch`。

14. **男歌女唱/女歌男唱升降调**：`f0_up_key` 建议 ±3 半音（《天下》初华 = +3）。同性别 0。`f0_method="rmvpe"`、`sid=0`、`rms_mix_rate=0.25`、`protect=0.33` 为实测稳定参数。

15. **混音参数**：`--vg 1.15 --ig 1.0 --peak 0.95`（人声略压伴奏、峰值归一 0.95 防削波）；人声太弱提 `--vg`，伴奏抢戏降 `--ig`。

## C. ASR / 打轴

16. **必须用整首正确歌词作 `initial_prompt`**：否则古风/粤语词错字率高（人名、方言字）。ASR 识别出的文本**只取时间戳，不取文字**——文字一律用原歌词（这就是 02 用 difflib 对齐的原因）。

17. **翻唱变声后人声识别率下降**：ASR 优先喂**变声前的原始人声**（`vocal_origin.wav`），时间轴与混音成片一致（未变速）。

18. **重复段必须按演唱顺序给足行数**（《天下》44 行 = 副歌唱 3 遍就出 3 组行）；间奏区间不留行。

19. **ASR 局部塌缩**：某段无声/异常时整段时间轴错位 → 对该区间单独切片复跑（`-ss 115 -t 55`），段内时间 + 偏移还原。

20. **小模型兜底**：无 GPU 用 `small` + `cpu` + `int8`（慢 5-10 倍但可用）；`vad_filter=True` 可跳过静音段减少误识别。

## D. 内容与流程

21. **角色形象设定（瞳色、服饰等）需 web_search 核实**，不要凭记忆编；歌词"谁唱的就用谁的人物"——翻唱对象是初华就用初华形象，不要混用其他角色。

22. **备份先行**：成片渲染前把旧输出改名 `_backup`（`shanghaitan_v8_backup.mp4`、`tianxia_final_backup_v4.mp4` 等均为历史备份），翻车可回滚。

23. **验证性探测优先**：任何新机器先跑探测脚本（ffmpeg 能力、dll 路径、UVR5 模型名、whisper 可用性），别一上来就全流程。

24. **分段渲染失败排查顺序**：命令长度（分更多段）→ 各段独立渲染验证（逐段生成 temp mp4 人工抽查）→ concat 参数一致性。
*（内容由AI生成，仅供参考）*
