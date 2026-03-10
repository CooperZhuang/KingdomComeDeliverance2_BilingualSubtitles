import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from localize_core import split_bilingual_text

OLLAMA_API_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3:latest"

TEST_XML_CONTENT = """
<Table>
<Row><Cell>achy_alchymist_a_je_to_a__n6s0</Cell><Cell>That's that! That was hard work!</Cell><Cell>就这样了！刚才真是场硬仗！ \\n That's that! That was hard work!</Cell></Row>
<Row><Cell>achy_alchymist_ale_jestli_XdGm</Cell><Cell>But if I ever run into that youngster again…</Cell><Cell>但如果再让我碰到那个年轻人… \n But if I ever run into that youngster again…</Cell></Row>
</Table>
"""


def create_ollama_prompt(
    original_chinese_translation: str, original_english_text: str
) -> str:
    return f"""
你是一位专业的游戏本地化翻译专家。你的任务是根据提供的英文原文，精校以下中文翻译，使其在游戏场景中更加地道、自然和精准。

英文原文：
"{original_english_text}"

当前中文翻译：
"{original_chinese_translation}"

请注意：
1. 你的回答必须仅包含精校后的中文文本，不要添加任何说明或解释。
2. 务必保留专有名词、人名、地名、技能名、物品名。
3. 在忠实原意的前提下，使译文符合中文玩家语言习惯，读起来自然流畅。
4. 保持原文语气、情感和风格，确保符合游戏场景。
5. 尽可能口语化，避免生硬直译。

精校后的中文翻译：
"""


def refine_translation(
    session: requests.Session,
    api_url: str,
    model: str,
    chinese_text: str,
    english_text: str,
    timeout: int,
) -> str:
    payload = {
        "model": model,
        "prompt": create_ollama_prompt(chinese_text, english_text),
        "stream": False,
        "options": {"temperature": 0.1},
    }

    response = session.post(api_url, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    return result.get("response", "").strip() or chinese_text


def process_localization_root(
    root: ET.Element,
    session: requests.Session,
    api_url: str,
    model: str,
    timeout: int,
) -> tuple[int, int]:
    processed_rows = 0
    skipped_rows = 0

    for index, row in enumerate(root.findall("Row"), start=1):
        cells = row.findall("Cell")
        if len(cells) < 3:
            skipped_rows += 1
            continue

        combined_text = cells[2].text or ""
        parts = split_bilingual_text(combined_text)
        if not parts:
            print(f"警告：第 {index} 行跳过，未识别到双语分隔符。")
            skipped_rows += 1
            continue

        original_chinese, original_english = parts
        print(f"\n--- 正在处理第 {index} 行 ---")
        print(f"英文: {original_english}")
        print(f"原中文: {original_chinese}")

        try:
            refined_chinese = refine_translation(
                session,
                api_url,
                model,
                original_chinese,
                original_english,
                timeout,
            )
        except requests.exceptions.RequestException as exc:
            print(f"Ollama API调用失败，保留原文: {exc}")
            refined_chinese = original_chinese

        cells[2].text = f"{refined_chinese}\\n{original_english}"
        print(f"精校后中文: {refined_chinese}")
        processed_rows += 1

    return processed_rows, skipped_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用 Ollama 精校双语字幕 XML")
    parser.add_argument("--input", type=Path, help="输入 XML 文件路径")
    parser.add_argument("--output", type=Path, help="输出 XML 文件路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama 模型名")
    parser.add_argument("--api-url", default=OLLAMA_API_URL, help="Ollama API 地址")
    parser.add_argument("--timeout", type=int, default=60, help="请求超时时间（秒）")
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="使用内置测试数据，不读取实际文件",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.test_mode:
        root = ET.fromstring(TEST_XML_CONTENT)
        output_path = args.output or Path("test_output.xml")
        input_label = "硬编码测试数据"
    else:
        if not args.input:
            print("错误：实际模式下必须提供 --input。")
            return 1
        if not args.input.exists():
            print(f"错误：输入文件不存在: {args.input}")
            return 1

        try:
            root = ET.parse(args.input).getroot()
        except ET.ParseError as exc:
            print(f"错误：XML解析失败: {exc}")
            return 1

        output_path = args.output or args.input.with_name(
            f"{args.input.stem}_refined{args.input.suffix}"
        )
        input_label = str(args.input)

    print(f"开始处理 {len(root)} 行数据 (数据源: {input_label})...")

    with requests.Session() as session:
        processed_rows, skipped_rows = process_localization_root(
            root, session, args.api_url, args.model, args.timeout
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)

    print("\n--- 任务完成 ---")
    print(f"已处理: {processed_rows} 行，跳过: {skipped_rows} 行")
    print(f"结果已保存至：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
