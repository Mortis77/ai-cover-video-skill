---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 9da29870b7dfe952a0e458cf6f69e3bd_1412c5c0cd2211f1afbb52540064ee0f
    ReservedCode1: BYNgIMN22Q86yhMWycIyVb/JciOGpnimmxTr5mdQ3QQtCWET9uqSTjnZZhChT4gIK5pqr2mqRU/AiXTb77ekGYcZ9NA92IRtdnGaNRdy73sveZuc801SlnwJ90fubjLlNfzPuFIWbkp+l9w4TJQdO82WTwxPa9mMXuPXxjOD8I1Eo+kN+SnhOPxNdUg=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 9da29870b7dfe952a0e458cf6f69e3bd_1412c5c0cd2211f1afbb52540064ee0f
    ReservedCode2: BYNgIMN22Q86yhMWycIyVb/JciOGpnimmxTr5mdQ3QQtCWET9uqSTjnZZhChT4gIK5pqr2mqRU/AiXTb77ekGYcZ9NA92IRtdnGaNRdy73sveZuc801SlnwJ90fubjLlNfzPuFIWbkp+l9w4TJQdO82WTwxPa9mMXuPXxjOD8I1Eo+kN+SnhOPxNdUg=
---

# 03 成片渲染（背景构图 + KTV 五行同屏滚动歌词）

> 模板脚本：`templates/render_ktv_template.py`（参数化：背景图/音频/SRT/歌名/输出路径/人物区域/歌词基准，含分段渲染+concat）。
> 真实链路参考：《上海滩》`temp\render_sht_gen8.py`（右对齐、歌名竖排左侧、全局 Q 表达式）；《天下》`temp\render_tianxia_v2.py`（居中偏右、歌名横排、分段渲染+concat）。

## 1. 流程总览

```
背景图({BG_IMAGE}) + 翻唱音频({MIX_WAV}) + SRT({SRT_IN})
   │
   ▼
① 背景构图分析：识别人物位置 → 字幕放留白侧、歌名放人物对侧
   ▼
② 生成每句歌词 textfile（UTF-8 无 BOM，相对路径，cwd=TEMP）★ 本机构建要求
   ▼
③ 构造五行同屏 drawtext filter（行1/2 已唱灰、行3 当前金、行4/5 未唱暗灰）
   ▼
④ 渲染：短歌单段直接渲染；长歌分段渲染 + concat（命令长度超限兜底）
   ▼
输出 {OUTPUT_MP4}
```

## 2. 背景构图分析（先分析再写坐标）

- 步骤：加载背景图 → 观察/识别**人物主体位置**（人物通常居中或偏一侧）→ 确定：
  - **歌词放留白侧**：人物偏左 → 歌词居中偏右或右对齐；人物居中 → 歌词放底部中央偏上（不挡脸）。
  - **歌名放人物对侧**：人物在左 → 歌名放右侧或顶部；人物在右 → 歌名放左（如《上海滩》人物偏右，歌名「上海灘」竖排左侧 x=430）。
- 实测构图（《天下》1024x768 人物偏左背景）：
  - 背景铺满：`scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080`（保人物全宽不横向裁切，仅裁上下）。
  - 歌词 `x='(w-text_w)/2+340'`（居中偏右），实测歌词最左 x≈1002px 不挡人物。
  - 歌名「天下」字号 64 金色白边、`y=120`、淡入 `alpha='clip(t*3,0,1)'`。
- 实测构图（《上海滩》）：歌词右对齐 `x='w-text_w-60'`；歌名「上海灘」三字竖排，字号 100，`x=430`（`x='xc-text_w/2'`），`y0=300`、字距 132。

## 3. KTV 五行同屏滚动歌词实现

### 3.1 布局参数（两首歌通用的"黄金参数"，实测满意）

| 参数 | 值 | 说明 |
|---|---|---|
| 画布 | 1920x1080 | 输出固定 |
| 字号 | 48 | 歌词行高 48px |
| 行距 | 138px | = 行高 48 + 空隙 90；五行总高 5*138 |
| 行3（当前句）y 顶 | 516 | 中心 540 = 画面中线（y=1080/2 上方留出歌名） |
| 五行 y | 516 / 378 / 240 / 792 / 654 | 行3=516，行1/2 上移、行4/5 下移（=516±138/±276） |
| 颜色 | 已唱 `0x8A8A8A@0.55`、当前 `0xFFDD88`、未唱 `0x555555@0.5` | 已唱灰 / 当前金 / 未唱暗灰 |
| 边框 | 当前 bw=2 白边；已唱/未唱 bw=1 半透明白边 | 文字可读性 |
| 滚动动画 | 0.5s 整组上移一行 | 每句切换时，最上一行滚出，新句底部进入 |

### 3.2 滚动原理（两种等价实现，脚本二选一）

**动画规则**：任意时刻，五行 = 已唱(2) + 当前(1) + 未唱(2)。每句开始时，当前句固定行3；前一句上移行2、再前一句上移行1后滚出；下两句进入行4/行5。

**方案 A：全局 Q 表达式（短歌/句数少，如《上海滩》12 句）**
```
Q(t) = -4 + Σ_k clip((t - s_k)/ROLL, 0, 1)     # s_k = 第 k 句 start，ROLL=0.5
行 i 的 y = 516 + (i-3)*138 - 138*Q(t)           # i = 句序号（0-based）
```
- 窗口 k0 内：前 k0+1 个 clip=1 → Q=k0-3 → 当前句 k0 恰好落在行3。
- 滚动：clip_{k0} 从 0→1 时 Q 平滑 +1，整组上移一行。
- **局限**：每句 y 都引用全部句的 clip（Σ 全展开），句数多了表达式爆炸 → 见方案 B。

**方案 B：局部 Σ + 分段渲染（长歌，如《天下》44 句）**
- 每层 drawtext 的 y 只保留**该层显示期起始之后才开启的窗口**：
  - 未唱层句 i：窗口从 `s[i-2]` 开启 → clip 项 k ∈ [i-2, i+3]；首句特例（i=1）用 `[s1, s2]` 窗口。
  - 当前层句 i：恒 `516`（无 Σ）。
  - 已唱层句 i：用**句结束时刻**触发上移 → `y = 378 - 138*(clip(e[i+1]) + clip(e[i+2]))`（e 为句结束）。
- **为什么"已唱层用句结束触发"**：句 i 唱完（e_i）到句 i+1 唱完（e_{i+1}）期间它在行2，e_{i+1} 后上移行1，e_{i+2} 后滚出。用句子结束时刻（而非下一句 start）保证切换节奏与演唱对齐。
- alpha 淡入淡出（两层夹击，任何一层用 clip 表达式即可）：
  - 当前层：`clip((t-s_i)*4,0,1) * clip((s_next - t)*4,0,1)`（0.25s 淡入 / 0.25s 淡出）
  - 未唱层：`clip((t-s_prev)*2,0,1) * clip((s_i - t)*4,0,1)`（0.5s 淡入）
  - 已唱层：`clip((t-s_next)*4,0,1) * clip((t_out - t)*4,0,1)`（t_out = s[i+3] 或 AUDIO_END）

### 3.3 ffmpeg filter 语法（本机 vision-bridge 构建，务必遵守）

- **drawtext 用 textfile 而非 text 内联**：横排 text 内联含空格会报错；歌词含空格/标点时尤其。
  ```text
  drawtext=fontfile={FONT}:textfile={LINE_FILE}:fontsize=48:fontcolor=0xFFDD88:
           borderw=2:bordercolor=white:
           x='(w-text_w)/2+340':y='{y_expr}':alpha='{alpha_expr}'
  ```
- **fontfile/textfile 必须相对路径 + 进程 cwd=TEMP**（vision-bridge 构建只解析相对路径；`subprocess.run(..., cwd=TEMP)`）。
- **y 表达式与 text 求值引擎分离**：本机构建中 y 的文本求值引擎与 text 不同，**避免"y=基准-偏移*共享变量"**；改成把共享变量直接展开成字面表达式（方案 B 已按此实现）。
- **背景铺满**：
  - 4:3/竖图：`scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p`（cover 裁上下，保人物全宽）
  - 横图 16:9：`scale=1920:1080,format=yuv420p`
- 歌名淡入：`alpha='clip(t*3,0,1)'`（前 0.33s 淡入）；竖排逐字实现：每个字一个 drawtext，`x='{xc}-text_w/2'`，`y={y0}+ci*{STEP}`。

### 3.4 分段渲染 + concat（长歌必经之路）

- **触发条件**：单条 `-filter_complex` 过长（>30000 字符 / Windows 命令行 32767 字符硬限）→ 分段。
- 做法：
  1. 按 SRT 时间轴切成 N 段（`render_tianxia_v2.py` 的 SEGS 即 4 段）；
  2. 每段 filtergraph 只含**本段显示期相交的层**（跨段句子在两段都生成对应层），每层表达式用**段内相对时间**（`s_local = s_global - T0`）；
  3. 逐段渲染临时 mp4（同编码参数）：
     ```text
     ffmpeg -y -loop 1 -t {dur} -i {BG} -ss {T0} -t {dur} -i {MIX_WAV}
            -filter_complex "{script}[v]" -map [v] -map 1:a
            -c:v libx264 -crf 19 -preset slow -pix_fmt yuv420p -c:a aac -b:a 192k
     ```
  4. concat 合并：
     ```text
     ffmpeg -y -i seg1.mp4 -i seg2.mp4 ... -filter_complex
            "[0:v][0:a][1:v][1:a]...concat=n=4:v=1:a=1[v][a]"
            -map [v] -map [a] -c:v libx264 -crf 19 -preset slow -pix_fmt yuv420p -c:a aac -b:a 192k out.mp4
     ```
- **备份先行**：输出已存在时先 `os.replace(out, out_backup.mp4)`。
- 段划分示例（《天下》4 段，见 `render_tianxia_v2.py` SEGS）：`(0.00,92.80)`、`(92.80,159.40)`、`(159.40,186.12)`、`(186.12,221.20)`；段边界取整句 start，跨段句在下一段重建该句的未唱/当前层。

## 4. 真实示例参数对照

| 参数 | 《上海滩》(render_sht_gen8.py) | 《天下》(render_tianxia_v2.py) |
|---|---|---|
| 背景 | `bg_image_1.jpg` | `bg_image_2.jpg`（1024x768） |
| 背景滤镜 | `scale=1920:1080` | `scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080` |
| 歌词对齐 | 右对齐 `x='w-text_w-60'` | 居中偏右 `x='(w-text_w)/2+340'` |
| 歌名 | 「上海灘」竖排 x=430、字号100、字距132、y0=300 | 「天下」横排字号64、y=120、淡入 |
| 滚动实现 | 方案 A（全局 Q，12 句单段） | 方案 B（局部 Σ + 4 段 concat，44 句） |
| 音频 | `temp\shanghaitan_mix3.wav`（AUDIO_END=194.18） | `output\tianxia_mix.wav`（AUDIO_END=221.20） |
| 输出 | `output\shanghaitan_final.mp4` | `output\tianxia_final.mp4` |

## 5. 校验清单

- [ ] 歌词不挡人物主体（构图分析先行）
- [ ] 当前句金色固定行3、已唱灰上滚、未唱暗灰下进（抽 3-4 个时间点看帧）
- [ ] 行距 138、无重叠无跳变
- [ ] 每句切换动画 0.5s 平滑（无瞬移）
- [ ] 输出时长为音频时长，音画同步
- [ ] 成片已备份（`_backup`）
*（内容由AI生成，仅供参考）*
