import xml.etree.ElementTree as ET
import requests
import json
import os # 导入 os 库，方便文件操作

# --- 配置 ---
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3:latest"  # 替换为你想要使用的Ollama模型
XML_FILE_PATH = 'game_localization.xml'
OUTPUT_FILE_PATH = 'game_localization_refined.xml'

# **【核心切换参数】**
# 设置为 True 时：运行测试用例，使用硬编码数据，输出文件名为 'test_output.xml'
# 设置为 False 时：运行实际文件，读取 XML_FILE_PATH，输出文件名为 OUTPUT_FILE_PATH
IS_TEST_MODE = True
# ----------------

# 准备测试数据（XML格式的字符串）
TEST_XML_CONTENT = """
<Table>
<Row><Cell>achy_alchymist_a_je_to_a__n6s0</Cell><Cell>That's that! That was hard work!</Cell><Cell>就这样了！刚才真是场硬仗！ \n That's that! That was hard work!</Cell></Row>
<Row><Cell>achy_alchymist_ale_jestli_XdGm</Cell><Cell>But if I ever run into that youngster again…</Cell><Cell>但如果再让我碰到那个年轻人… \n But if I ever run into that youngster again…</Cell></Row>
<Row><Cell>achy_alchymist_aspon_zije_UWNH</Cell><Cell>At least we're alive… I reckon that'll do for today.</Cell><Cell>至少我们还活着…我想今天就这样吧。 \n At least we're alive… I reckon that'll do for today.</Cell></Row>
<Row><Cell>achy_alchymist_haha_y9CT</Cell><Cell>Haha!</Cell><Cell>哈哈！ \n Haha!</Cell></Row>
<Row><Cell>achy_alchymist_mel_vrazdu_LaNq</Cell><Cell>He had murder in his eyes…</Cell><Cell>他眼中充满杀意… \n He had murder in his eyes…</Cell></Row>
<Row><Cell>achy_alchymist_tak_tohle__d1im</Cell><Cell>That was a close one.</Cell><Cell>刚才可真是好险哪。 \n That was a close one.</Cell></Row>
<Row><Cell>achy_alchymist_ten_kluk_b_HUao</Cell><Cell>That lad must've been mad.</Cell><Cell>那个小伙子一定是疯了。 \n That lad must've been mad.</Cell></Row>
<Row><Cell>achy_alchymist_to_by_nas__wqi5</Cell><Cell>Those bones would have cost us dearly.</Cell><Cell>那些骨头差点让我们付出巨大的代价。 \n Those bones would have cost us dearly.</Cell></Row>
<Row><Cell>achy_alchymist_uff_RCen</Cell><Cell>Phew...</Cell><Cell>吁… \n Phew...</Cell></Row>
<Row><Cell>achy_alchymist_uff_VI2a</Cell><Cell>Oof…</Cell><Cell>哎哟… \n Oof…</Cell></Row>
<Row><Cell>a_co_henry_a_co_dal_hanse_YOgx</Cell><Cell>What next? I found Janosh, but where the fuck is Adder?</Cell><Cell>然后呢？我找到了亚诺什，但阿德尔他妈的在哪？ \n What next? I found Janosh, but where the fuck is Adder?</Cell></Row>
<Row><Cell>a_co_henry_a_co_ted_porad_abfK</Cell><Cell>What now? I still don't know where Janosh is.</Cell><Cell>现在怎么办？我还是不知道亚诺什在哪里。 \n What now? I still don't know where Janosh is.</Cell></Row>
</Table>
"""

def create_ollama_prompt(original_chinese_translation, original_english_text):
    """
    构造用于精校翻译的Prompt。
    """
    prompt = f"""
你是一位专业的游戏本地化翻译专家。你的任务是根据提供的英文原文，**精校**以下中文翻译，使其在游戏场景中更加地道、自然和精准。

**英文原文：**
"{original_english_text}"

**当前中文翻译：**
"{original_chinese_translation}"

**请注意：**
1. 你的回答必须**仅包含**精校后的中文文本，不要添加任何说明、解释或额外标点（例如：不要说“精校后的中文是：”）。
2. 务必完整保留原文中的专有名词、人名、地名、技能名、物品名等，不要随意改动或替换。
3. 在保证忠实原意的前提下，使译文符合中文玩家的语言习惯，读起来自然流畅，避免生硬直译。
4. 保持原文的语气、情感和风格（如紧张、幽默、史诗感等），确保符合游戏场景氛围。
5. 尽可能口语化，不要书面化用于。

精校后的中文翻译：
"""
    return prompt

def refine_translation(chinese_text, english_text):
    """
    调用Ollama API进行翻译精校。
    """
    prompt = create_ollama_prompt(chinese_text, english_text)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
        }
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status() # 检查HTTP错误

        result = response.json()
        refined_text = result.get('response', '').strip()
        return refined_text

    except requests.exceptions.RequestException as e:
        print(f"Ollama API调用失败: {e}")
        # **【测试/错误处理差异】** # 测试模式下，为了验证流程，可以返回一个特殊标记；实际模式下，最好返回原文。
        if IS_TEST_MODE:
             return f"[TEST_ERROR] {chinese_text}"
        else:
             return chinese_text # 实际处理时，失败了就保留原文，避免丢失数据

def process_localization_file(is_test_mode):
    """
    主处理函数：根据模式选择数据源，调用Ollama，并保存结果。
    """
    if is_test_mode:
        print("--- 运行模式：测试模式 ---")
        # 从硬编码字符串加载数据
        root = ET.fromstring(TEST_XML_CONTENT)
        input_name = "硬编码测试数据"
        output_name = 'test_output.xml'
    else:
        print("--- 运行模式：实际文件模式 ---")
        input_name = XML_FILE_PATH
        output_name = OUTPUT_FILE_PATH
        
        try:
            # 从实际文件加载数据
            tree = ET.parse(XML_FILE_PATH)
            root = tree.getroot()
        except FileNotFoundError:
            print(f"错误：文件未找到：{XML_FILE_PATH}")
            return
        except ET.ParseError as e:
            print(f"错误：XML解析失败：{e}")
            return


    print(f"开始处理 {len(root)} 行数据 (数据源: {input_name})...")

    # 遍历每一个 <Row> 元素
    for i, row in enumerate(root.findall('Row')):
        cells = row.findall('Cell')

        if len(cells) < 3:
            continue

        # 提取第三个单元格的内容
        combined_text = cells[2].text
        if not combined_text or '\n' not in combined_text:
            print(f"警告：第 {i+1} 行跳过格式不正确的行。")
            continue

        # 使用 \n 分割，获取中文翻译和英文原文
        parts = combined_text.split('\n', 1)
        original_chinese = parts[0].strip()
        original_english = parts[1].strip()

        print(f"\n--- 正在处理第 {i+1} 行 ---")
        print(f"英文: {original_english}")
        print(f"原中文: {original_chinese}")

        # 调用Ollama进行精校
        refined_chinese = refine_translation(original_chinese, original_english)

        print(f"精校后中文: {refined_chinese}")

        # 更新第三个单元格的内容 (保持格式：中文\n英文)
        new_combined_text = f"{refined_chinese}\n{original_english}"
        cells[2].text = new_combined_text

    # 将修改后的数据保存到文件
    if is_test_mode:
        # 测试模式下，创建一个新的ElementTree来保存结果
        new_tree = ET.ElementTree(root)
        new_tree.write(output_name, encoding='utf-8', xml_declaration=True)
    else:
        # 实际文件模式下，使用原始的 tree 对象（如果成功解析的话）
        # 注意：这里需要确保 tree 变量在非测试模式下是存在的
        # 简单的做法是重新构造 tree
        tree = ET.ElementTree(root)
        tree.write(output_name, encoding='utf-8', xml_declaration=True)
    
    print(f"\n--- 任务完成 ---")
    print(f"结果已保存至：{output_name}")

# --- 主程序入口 ---
if __name__ == "__main__":
    # **在你运行代码时，手动修改顶部的 `IS_TEST_MODE` 变量即可切换模式。**

    # 运行实际文件模式时，请确保 `XML_FILE_PATH` 文件存在。
    # 如果你使用我之前创建的临时文件，可以在运行前手动创建它：
    if not os.path.exists(XML_FILE_PATH) and not IS_TEST_MODE:
        print(f"\n注意：{XML_FILE_PATH} 不存在，已自动创建示例文件。")
        temp_xml_content_full = """
<LocalizationData>
<Row><Cell>achy_alchymist_a_je_to_a__n6s0</Cell><Cell>That's that! That was hard work!</Cell><Cell>就这样了！刚才真是场硬仗！ \n That's that! That was hard work!</Cell></Row>
<Row><Cell>achy_alchymist_ale_jestli_XdGm</Cell><Cell>But if I ever run into that youngster again…</Cell><Cell>但如果再让我碰到那个年轻人… \n But if I ever run into that youngster again…</Cell></Row>
<Row><Cell>achy_alchymist_aspon_zije_UWNH</Cell><Cell>At least we're alive… I reckon that'll do for today.</Cell><Cell>至少我们还活着…我想今天就这样吧。 \n At least we're alive… I reckon that'll do for today.</Cell></Row>
</LocalizationData>
"""
        with open(XML_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(temp_xml_content_full)

    process_localization_file(IS_TEST_MODE)