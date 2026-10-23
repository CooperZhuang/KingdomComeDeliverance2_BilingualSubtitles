# AI 中文配音（TTS 批量合成）

把 `text_ui_dialog.xml` 里的对话逐条送去本地 Gradio TTS 服务合成中文语音，再转成游戏用的 ogg。

这是公开仓库里原本没有的一段：字幕是「看」，这条流水线是「听」，两者共用同一份对话 XML。

## 三个脚本

| 文件 | 作用 |
| --- | --- |
| `voiceover_processor.py` | 主流程：解析对话 XML → 按角色/语气映射音色 → 并发调用 TTS → 分角色输出 wav；支持多 TTS 实例轮询与优雅停止 |
| `stop_processor.py` | 写 `stop_flag.txt`，让正在跑的主流程在下一个断点退出（几万条对话不能只靠 Ctrl+C） |
| `wav2ogg.py` | 用 ffmpeg 批量把 wav 转 ogg（游戏要的格式），多进程并行 + 进度显示 |

## 用法

```bash
pip install -r requirements.txt          # 只有 gradio-client
# 先起一个或多个本地 TTS 服务（默认 127.0.0.1:7860 的 /gen_single 接口）
python voiceover_processor.py            # 需要同目录有 text_ui_dialog.xml
python wav2ogg.py                        # 把 中文配音输出/ 转成 中文配音ogg/
```

- TTS 服务地址在 `voiceover_processor.py` 顶部的 `TTS_CLIENT_URLS` 里改，`MAX_WORKERS` 控制并发。
- ffmpeg 位置：优先环境变量 `FFMPEG`，其次 `PATH`，最后才回落硬编码路径。
- 输入 XML 文件名固定为 `text_ui_dialog.xml`，放在脚本同目录。

## 为什么只放代码，不放数据

`text_ui_dialog.xml`、`中文配音输出/`、生成的 ogg 都含《天国：拯救 2》的游戏原文与音频，**版权归开发商所有，一律不进仓库**（`.gitignore` 已挡住）。仓库里只有处理逻辑，数据请你从自己合法的游戏安装目录里取。
