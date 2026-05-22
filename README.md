# Kingdom Come Deliverance 2 双语字幕工具包

## 项目简介

这个仓库提供两个工具：

- `天国拯救2_双语_全自动.py`：主处理脚本，用于解压游戏 PAK、合并人工修正、生成双语字幕并重新打包。
- `AI精校.py`：辅助精校脚本，用于把已有双语 XML 逐行发送给本地 Ollama 模型做中文润色。

仓库不再维护 `v1` / `v2` 双版本，当前只保留一个正式入口。

## 环境要求

- Windows 10/11
- Python 3.9+
- 可选依赖：`requests`
- 可选服务：Ollama（仅 `AI精校.py` 需要）

安装可选依赖：

```bash
pip install requests
```

## 主处理脚本

默认会处理：

- 原始包：`Localization/Chineses_xml.pak`
- 修正包：`Mods/chinesesfixptf/Localization/Chineses_xml.pak`
- 目标 XML：`text_ui_dialog.xml`

运行：

```bash
python 天国拯救2_双语_全自动.py
```

常用参数：

```bash
python 天国拯救2_双语_全自动.py --steam-path "D:/SteamLibrary/steamapps/common/KingdomComeDeliverance2"
python 天国拯救2_双语_全自动.py --target-file text_ui_dialog.xml --target-file text_ui_book.xml
python 天国拯救2_双语_全自动.py --use-backup-as-source
python 天国拯救2_双语_全自动.py --keep-temp
```

行为说明：

- 每次运行前都会清空 `temp_processing/`，避免脏数据混入。
- 默认优先使用当前修正包作为修正源；只有显式传 `--use-backup-as-source` 才会读取 `.pak.backup`。
- 如果修正记录已全部被使用，不会再因为缺少 `text__chinesesfixptf.xml` 而失败。

## AI 精校脚本

支持两种 API 协议：

- **Ollama**（默认）：本地部署，无需 API Key
- **OpenAI 兼容**：DeepSeek、OpenAI 等云端模型

### Ollama（本地）

先启动 Ollama，并确保模型可用，例如：

```bash
ollama serve
ollama pull qwen3:latest
```

处理实际文件：

```bash
python AI精校.py --input game_localization.xml
```

指定输出文件或模型：

```bash
python AI精校.py --input game_localization.xml --output game_localization_refined.xml
python AI精校.py --input game_localization.xml --model qwen3:latest
python AI精校.py --input game_localization.xml --api-url http://localhost:11434/api/generate
python AI精校.py --input game_localization.xml --timeout 120
```

### OpenAI 兼容接口（DeepSeek 等）

```bash
# DeepSeek（默认 base URL）
python AI精校.py --input game_localization.xml --provider openai --api-key sk-xxxx

# 自定义 API 地址
python AI精校.py --input game_localization.xml --provider openai \
  --api-url https://api.openai.com/v1/chat/completions \
  --model gpt-4o --api-key sk-xxxx

# 使用环境变量
export OPENAI_API_KEY=sk-xxxx
python AI精校.py --input game_localization.xml --provider openai
```

### 测试模式

```bash
python AI精校.py --test-mode
```

兼容格式：

- `中文 \n 英文`
- `中文` + 实际换行 + `英文`

## 双语规则

- 默认连接符：`" \\n "`
- `ui_nm` 前缀：使用两个空格连接中英文

示例：

- 普通文本：`中文内容 \n English text`
- UI 名称：`中文名称  English Name`

## 测试

仓库附带最小回归测试，覆盖：

- 双语分隔兼容性
- 修正记录消费逻辑
- 无剩余修正时的正常行为
- 临时目录清理
- 默认修正源选择

运行：

```bash
python -m unittest discover -s tests -v
```

## 代码结构

```text
.
├── localize_core.py            # 共享核心库：PAK 解压/打包、XML 处理、双语合并
├── 天国拯救2_双语_全自动.py      # 主处理脚本：编排完整的自动化流水线
├── AI精校.py                    # 辅助脚本：通过 Ollama 精校双语字幕
└── tests/
    └── test_localize_core.py    # 单元测试
```
