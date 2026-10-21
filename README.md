# ai-cover-video-skill

AI 翻唱 MV 制作技能包：从原曲到成片的端到端流程（人声分离 → RVC 变声 → 歌词 ASR 打轴 → KTV 字幕渲染 → 混音成片），含参数化模板脚本与 24 条踩坑清单。

## 目录结构

```
ai_cover_video_skill/
├── SKILL.md                    # 技能入口：流程总览、前置依赖、参数说明
├── 01_audio_制作音频.md        # 步骤一：转 wav → UVR5 分离 → RVC 变声 → 混音
├── 02_asr_歌词打轴.md          # 步骤二：faster-whisper 识别歌词并生成 SRT
├── 03_render_成片.md           # 步骤三：FFmpeg 渲染 KTV 字幕成片
├── 04_gotchas_踩坑清单.md      # 24 条实测踩坑记录
└── templates/
    ├── audio_pipeline_template.py  # 音频全流程模板（转码/分离/变声/混音）
    ├── asr_lyrics_template.py      # ASR 歌词打轴模板
    └── render_ktv_template.py      # KTV 字幕渲染模板
```

## 使用方式

1. 阅读 `SKILL.md` 了解整体流程与前置依赖。
2. 将 `templates/` 下三个模板复制为你的脚本，把其中的 `{占位符}` 替换为实际路径/参数。
3. 按 `01 → 02 → 03` 顺序执行三个步骤。
4. 遇到问题先查 `04_gotchas_踩坑清单.md`。

## 前置依赖

| 组件 | 用途 |
|---|---|
| ffmpeg | 渲染 / 混音 / 切片 |
| RVC Core（含 UVR5） | 人声/伴奏分离 + 变声推理 |
| faster-whisper | 歌词 ASR 打轴 |
| Python（librosa + soundfile） | 混音 / 重采样 |

## 参数化说明

所有模板均已参数化，路径用 `{ORIGINAL_AUDIO}`、`{VOCAL_MODEL}`、`{BG_IMAGE}` 等占位符，示例值使用通用路径（`C:\path\to\...`）。请替换为你自己的实际路径后再运行。

## License

[MIT](LICENSE)
