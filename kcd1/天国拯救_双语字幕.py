import argparse
import os
import re
import string
import xml.etree.ElementTree as ET


# 加载翻译源文件
def load_translation_source(source_file):
    translation_map = {}
    try:
        tree = ET.parse(source_file)
        root = tree.getroot()

        # 遍历每一行
        for row in root.findall("Row"):
            cell1 = row.find("Cell[1]")
            cell3 = row.find("Cell[3]")
            # 如果第一列和第三列都不为空，则将第一列的文本作为键，第三列的文本作为值，存入translation_map字典中
            if cell1 is not None and cell3 is not None:
                translation_map[cell1.text] = cell3.text
    except Exception as e:
        print(f"加载翻译源文件时出现错误: {e}")
    return translation_map


# 加载文本修正
def load_corrections():
    corrections = {
        "我感觉整个整个波罗的海都被我喝下去了！": "感觉我喝了整个波罗的海！",
        "桐乡": "同乡",
        "魔人的小妖精": "迷人精",
        "拿者": "拿着",
        "靠的住": "靠得住",
        "那你的东西": "拿你的东西",
        "翰纳什的公子": "韩内津·黑尔",
        "汗死卡彭": "汉斯卡蓬",
        "韩內津": "韩内津",
        "包头": "爆头",
        "亡灵之书": "死灵之书",
        "形而上学": "玄学",
        "治愈之书": "医书",
        "外瑞": "薇芮",
        "格特鲁德": "葛翠特",
        "皮社科": "佩谢克",
        "巴纳德长官": "巴纳德队长",
        "瑞奇": "臭佬",
        "战马杰达": "战马扬达",
        "寇奔庄园": "科尔本农场",
        "寇奔农场": "科尔本农场",
        "蔻奔庄园": "科尔本农场",
        "蔻奔农场": "科尔本农场",
        "戴卫斯": "迪维什",
        "戴维斯": "迪维什",
        "阿里伊本新浪": "阿里·胡赛恩·伊本·席纳",
        "伊本西纳": "伊本·席纳",
        "皮克施泰因": "皮克斯坦因",
        "西尔伯·斯卡里茨": "银之斯卡里茨",
        "”臭佬“汤达": "“恶臭”汤达",
        "莫霍杰德": "莫霍耶茨",
    }
    return corrections


# 应用文本修正
def apply_corrections(text, corrections):
    for key, value in corrections.items():
        text = text.replace(key, value)
    return text


def contains_chinese(text):
    # 使用正则表达式检查文本中是否包含中文字符
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def is_ending_with_punctuation(text):
    # 定义包括英文标点和常见中文全角标点的符号
    punctuation = string.punctuation + "，。！？；：、（）《》“”‘’【】"
    return text and text[-1] in punctuation


def merge_cells_in_row(row, translation_map, corrections):
    cell1 = row.find("Cell[1]")
    cell2 = row.find("Cell[2]")
    cell3 = row.find("Cell[3]")

    if cell1 is not None and cell2 is not None and cell3 is not None:
        # 检查第二个单元格是否是 "<...>"
        if cell2.text == "<...>":
            return

        # 如果第三个单元格的文本中不包含中文字符，不进行拼接
        if not contains_chinese(cell3.text):
            return

        if cell1.text in translation_map:
            translated_text = translation_map[cell1.text]
        else:
            translated_text = cell3.text

        # 检查是否包含特殊的HTML标签
        if "<br/>&nbsp;<br/>" in translated_text:
            separator = "<br/>&nbsp;<br/>"
        elif is_ending_with_punctuation(translated_text.strip()):
            separator = "<br/>"
        else:
            separator = " / "

        merged_text = f"{translated_text}{separator}{cell2.text}"

        # 应用文本修正
        cell3.text = apply_corrections(merged_text, corrections)


# 处理XML文件
def process_xml_file(input_file, output_file, translation_map, corrections):
    try:
        tree = ET.parse(input_file)
        root = tree.getroot()

        # 遍历每一行
        for row in root.findall("Row"):
            merge_cells_in_row(row, translation_map, corrections)

        # 将处理后的XML文件写入输出文件
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        print(f"处理完成：{input_file} -> {output_file}")
    except Exception as e:
        print(f"处理文件 {input_file} 时出现错误: {e}")


# 处理XML目录
def process_xml_directory(input_dir, output_dir, translation_source):
    translation_map = load_translation_source(translation_source)
    corrections = load_corrections()

    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 遍历输入目录中的所有文件
    for filename in os.listdir(input_dir):
        # 如果文件是XML文件
        if filename.endswith(".xml"):
            input_file = os.path.join(input_dir, filename)
            output_file = os.path.join(output_dir, filename)
            # 处理XML文件
            process_xml_file(input_file, output_file, translation_map, corrections)


def main(argv=None):
    parser = argparse.ArgumentParser(description="KCD1 双语字幕生成：把中文原版 XML 逐文件生成中英双语版")
    here = os.path.dirname(os.path.abspath(__file__))
    lang_dir = os.path.join(here, "天国拯救语言文件")
    parser.add_argument(
        "--input-dir", default=os.path.join(lang_dir, "中文原版"), help="中文原版 XML 目录"
    )
    parser.add_argument(
        "--output-dir", default=os.path.join(lang_dir, "双语版"), help="输出目录"
    )
    parser.add_argument(
        "--source",
        default=os.path.join(lang_dir, "text__ChineseUpdated_source.xml"),
        help="翻译源表（Row/Cell 结构）",
    )
    args = parser.parse_args(argv)
    process_xml_directory(args.input_dir, args.output_dir, args.source)


if __name__ == "__main__":
    main()
