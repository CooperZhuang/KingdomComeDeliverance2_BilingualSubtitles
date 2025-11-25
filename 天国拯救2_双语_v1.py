import copy
import os
import xml.etree.ElementTree as ET
import zipfile

# ----------------- 配置区 -----------------
# 文件路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 默认子文件夹名
ORIGINAL_FOLDER_NAME = "原始文件"
CORRECTION_FOLDER_NAME = "修正文件"

# 修正文件的输入/输出配置
# 修正文件输入/输出的文件名（保持一致）
CORRECTION_INPUT_FILENAME = "text__chinesesfixptf.xml"
REMAINING_CORRECTION_OUTPUT_FILENAME = CORRECTION_INPUT_FILENAME
PAK_OUTPUT_FILENAME = "Chineses_xml.pak"  # 最终的 PAK 档案文件名

# 完整文件夹路径
ORIGINAL_FOLDER = os.path.join(BASE_DIR, ORIGINAL_FOLDER_NAME)
CORRECTION_FOLDER = os.path.join(BASE_DIR, CORRECTION_FOLDER_NAME)
CORRECTION_FILE_PATH = os.path.join(CORRECTION_FOLDER, CORRECTION_INPUT_FILENAME)
PAK_OUTPUT_PATH = os.path.join(BASE_DIR, PAK_OUTPUT_FILENAME)
# ------------------------------------------


# 简化了连接符获取逻辑，更易读
def get_connector(unique_id: str) -> str:
    """
    根据 ID 规则获取合并文本时使用的连接符。
    规则：如果 ID 以 'ui_nm' 开头，连接符为空，否则为 "\n"。
    返回结果是包含空格的连接符，例如 " \n " 或 "  "。
    """
    # 默认连接符为 Python 字符串换行符
    connector_char = ""

    if unique_id and unique_id.startswith("ui_nm"):
        connector_char = ""
    else:
        # 使用 \n 字符作为换行符
        connector_char = "\\n"

    # 返回带空格的连接符，兼容原始代码的格式
    return f" {connector_char} "


def write_compact_xml(root: ET.Element, path: str) -> bool:
    """
    使用 ElementTree 写入 XML 文件，并手动插入换行符以实现 <Table>\n<Row> 格式。
    此方法用于生成精确的、不带 XML 声明和缩进的 XML 文件。
    """
    try:
        # 1. 生成紧凑的 XML 字符串（无声明，无默认缩进）
        # short_empty_elements=False 确保空标签不会自闭合
        xml_string = ET.tostring(
            root, encoding="utf-8", short_empty_elements=False
        ).decode("utf-8")

        # 2. 插入换行符以满足格式要求：
        # Step A: 插入换行符在父子元素之间，实现 <Table>\n<Row> 和 </Row>\n<Row>
        # 查找所有紧邻的父子标签连接（例如 `><Row>` 或 `</Row><Row>`) 并插入换行
        xml_string = xml_string.replace("><Row>", ">\n<Row>")

        # Step B: 插入换行符在根元素结束前，实现 ...</Row>\n</Table>
        xml_string = xml_string.replace("</Row></Table>", "</Row>\n</Table>")

        with open(path, "w", encoding="utf-8") as f:
            f.write(xml_string)

        return True
    except Exception as e:
        print(f"❌ 写入文件 {path} 时发生错误: {e}")
        return False


def read_corrections_data(correction_path: str) -> tuple[dict, dict]:
    """
    读取修正文件，返回 ID 到修正文本的映射 (map) 和 ID 到完整 Row 元素的映射 (rows)。
    """
    correction_map = {}
    correction_rows = {}

    try:
        print(f"尝试读取修正文件: {correction_path}")
        tree_corr = ET.parse(correction_path)
        root_corr = tree_corr.getroot()

        for row in root_corr.findall("Row"):
            cells = row.findall("Cell")

            # 确保至少有3个 Cell 元素
            if len(cells) >= 3:
                unique_id = cells[0].text
                # 使用 cells[2].text or "" 来简洁处理 None 值
                corrected_chinese = cells[2].text or ""

                if unique_id:
                    # 存储中文修正文本
                    correction_map[unique_id] = corrected_chinese
                    # 存储完整的 Row 元素副本，用于追踪哪些被使用了
                    correction_rows[unique_id] = copy.deepcopy(row)

        print(f"✅ 已从修正文件读取 {len(correction_map)} 条修正记录。")
        return correction_map, correction_rows
    except FileNotFoundError:
        print(f"⚠️ 警告：修正文件未找到，路径: {correction_path}。将跳过修正步骤。")
    except Exception as e:
        print(f"⚠️ 警告：解析修正文件失败 ({e})。将跳过修正步骤。错误: {e}")

    return correction_map, correction_rows  # 即使失败，也返回空字典，防止 None 错误


def process_single_file(
    original_file_path: str, correction_map: dict, correction_rows: dict
) -> str | None:
    """
    处理单个原始 XML 文件，应用修正，执行双语化，并删除 correction_rows 中匹配的记录。
    返回生成的双语 XML 文件的路径。
    注意：correction_rows 是通过引用传递的，因此修改它会影响主程序中的字典。
    """
    original_filename = os.path.basename(original_file_path)
    # 根据需求 2，输出到 BASE_DIR，文件名与原文件一致
    output_xml_path = os.path.join(BASE_DIR, original_filename)

    print(f"\n--- 1.1 正在处理原始文件: {original_filename} ---")

    try:
        tree_orig = ET.parse(original_file_path)
        root_orig = tree_orig.getroot()
    except Exception as e:
        print(f"❌ 错误：读取或解析原始文件 '{original_filename}' 失败 ({e})。跳过。")
        return None

    applied_count = 0
    total_rows = 0

    # 临时存储需要从 correction_rows 中删除的 ID，避免在迭代时修改字典
    ids_to_delete = set()

    for row in root_orig.findall("Row"):
        total_rows += 1
        cells = row.findall("Cell")

        if len(cells) == 3:
            unique_id = cells[0].text
            english_cell = cells[1]
            chinese_cell = cells[2]

            english_text = english_cell.text or ""
            original_chinese_text = chinese_cell.text or ""

            final_chinese_text = original_chinese_text

            # **应用修正**
            if unique_id in correction_map:
                final_chinese_text = correction_map[unique_id]
                applied_count += 1

                # **根据需求 3，标记修正记录为已使用**
                if unique_id in correction_rows:
                    ids_to_delete.add(unique_id)

            # **双语化**：中文 + 连接符 + 英文
            connector = get_connector(unique_id or "")
            combined_text = f"{final_chinese_text}{connector}{english_text}"
            chinese_cell.text = combined_text

    # 实际删除已使用的修正记录
    for unique_id in ids_to_delete:
        if unique_id in correction_rows:
            del correction_rows[unique_id]

    print(
        f"🔄 文件 '{original_filename}' 处理完毕。总记录 {total_rows} 条，应用修正 {applied_count} 条。"
    )

    # 写入双语化后的文件
    if write_compact_xml(root_orig, output_xml_path):
        print(f"🎉 双语文件保存至: **{original_filename}**")
        return output_xml_path
    else:
        return None


def write_remaining_corrections(
    correction_rows: dict, output_filename: str
) -> str | None:
    """
    将 correction_rows 中剩余未匹配的 Row 写入新的 XML 文件。
    这个文件将作为补充文件一并打包。
    """

    if not correction_rows:
        print("ℹ️ 修正文件中所有记录均已被原始文件使用，无需生成剩余修正文件。")
        return None

    print(f"\n--- 2. 正在生成剩余修正文件: {output_filename} ---")

    # 根据用户要求，确保 XML 根元素名称为 <Table>。
    root = ET.Element("Table")

    # 循环追加剩余的 Row 元素
    for row in correction_rows.values():
        root.append(row)

    output_path = os.path.join(BASE_DIR, output_filename)

    if write_compact_xml(root, output_path):
        print(
            f"➕ 已将修正文件中未使用的 {len(correction_rows)} 条记录保存为: **{output_filename}**"
        )
        return output_path
    else:
        return None


def create_pak_archive(files_to_package: list[str], pak_output_path: str):
    """
    将指定的 XML 文件列表压缩成单个 PAK 档案（ZIP_DEFLATED 模式）。
    """
    if not files_to_package:
        print("❌ 错误：没有文件需要打包。跳过 PAK 生成。")
        return

    print(f"\n--- 3. 开始执行 PAK 文件打包：{PAK_OUTPUT_FILENAME} ---")

    try:
        # 使用 'w' 模式写入，zipfile.ZIP_DEFLATED 指定压缩方式
        # 如果文件已存在，会被覆盖
        with zipfile.ZipFile(pak_output_path, "w", zipfile.ZIP_DEFLATED) as pak_file:
            for file_path in files_to_package:
                if not os.path.exists(file_path):
                    print(f"⚠️ 警告：文件 '{file_path}' 不存在，跳过打包。")
                    continue

                # 获取文件在 PAK 内部的名称
                internal_filename = os.path.basename(file_path)

                # 将文件写入 PAK 档案
                pak_file.write(file_path, internal_filename)

                print(f"📦 已打包: '{internal_filename}'")

                # **删除中间生成的 XML 文件**
                os.remove(file_path)
                print(f"🗑️ 已删除中间文件: {internal_filename}")

        print(f"🎉 PAK 打包成功！文件保存至: **{PAK_OUTPUT_FILENAME}**")

    except Exception as e:
        print(f"❌ 错误：打包过程中发生异常: {e}")


if __name__ == "__main__":
    # 确保子文件夹存在
    os.makedirs(ORIGINAL_FOLDER, exist_ok=True)
    os.makedirs(CORRECTION_FOLDER, exist_ok=True)

    print(
        f"⚠️ **流程说明：** 脚本将遍历 '{ORIGINAL_FOLDER_NAME}' 文件夹下的所有 XML 文件，应用 '{CORRECTION_FOLDER_NAME}' 文件夹中的修正，并将所有生成的双语文件和修正文件中剩余的内容一起打包为 **{PAK_OUTPUT_FILENAME}**，随后删除所有中间生成的 XML 文件。"
    )

    # 1. 初始化修正数据
    # correction_rows 字典用于跟踪哪些修正记录还未被原始文件使用。
    correction_map, correction_rows = read_corrections_data(CORRECTION_FILE_PATH)

    generated_xml_files = []

    # 2. 遍历并处理所有原始 XML 文件 (需求 1)
    print("\n--- 1. 开始执行原始文件批量合并 ---")
    try:
        # 查找所有以 .xml 结尾的文件
        xml_files = [f for f in os.listdir(ORIGINAL_FOLDER) if f.endswith(".xml")]
    except FileNotFoundError:
        print(
            f"❌ 错误：原始文件目录 '{ORIGINAL_FOLDER_NAME}' 不存在，请创建该目录并放入原始 XML 文件。"
        )
        xml_files = []

    if not xml_files:
        print("ℹ️ 未在原始文件目录中找到任何 XML 文件。")

    for filename in xml_files:
        original_file_path = os.path.join(ORIGINAL_FOLDER, filename)
        # correction_rows 字典在这里通过引用传递，并在函数内部删除已匹配的记录。
        merged_file_path = process_single_file(
            original_file_path, correction_map, correction_rows
        )
        if merged_file_path:
            generated_xml_files.append(merged_file_path)

    # 3. 写入修正文件中剩余未使用的内容 (需求 3)
    remaining_correction_path = write_remaining_corrections(
        correction_rows, REMAINING_CORRECTION_OUTPUT_FILENAME
    )
    if remaining_correction_path:
        generated_xml_files.append(remaining_correction_path)

    # 4. 打包所有生成的 XML 文件 (需求 2)
    create_pak_archive(generated_xml_files, PAK_OUTPUT_PATH)
