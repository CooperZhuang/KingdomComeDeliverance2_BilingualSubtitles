import copy
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class AutoLocalizationProcessor:
    """天国拯救2本地化文件自动化处理器"""

    def __init__(self):
        # 配置路径
        self.steam_path = Path(
            "C:/Program Files (x86)/Steam/steamapps/common/KingdomComeDeliverance2"
        )
        self.original_pak_path = self.steam_path / "Localization/Chineses_xml.pak"
        self.correction_pak_path = (
            self.steam_path / "Mods/chinesesfixptf/Localization/Chineses_xml.pak"
        )
        self.correction_backup_path = self.correction_pak_path.with_suffix(
            ".pak.backup"
        )
        self.output_pak_path = self.correction_pak_path  # 输出到修正文件路径

        # 工作目录
        self.work_dir = Path(__file__).parent
        self.temp_dir = self.work_dir / "temp_processing"
        self.original_xml_dir = self.temp_dir / "original_xml"
        self.correction_xml_dir = self.temp_dir / "correction_xml"

        # 确保工作目录存在
        self.temp_dir.mkdir(exist_ok=True)
        self.original_xml_dir.mkdir(exist_ok=True)
        self.correction_xml_dir.mkdir(exist_ok=True)

    def extract_pak_file(self, pak_path: Path, extract_dir: Path) -> bool:
        """解压pak文件到指定目录"""
        try:
            if not pak_path.exists():
                print(f"❌ 错误：pak文件不存在: {pak_path}")
                return False

            print(f"📦 正在解压: {pak_path.name}")

            with zipfile.ZipFile(pak_path, "r") as pak_file:
                pak_file.extractall(extract_dir)

            print(f"✅ 解压完成: {extract_dir}")
            return True

        except Exception as e:
            print(f"❌ 解压失败: {e}")
            return False

    def get_connector(self, unique_id: Optional[str]) -> str:
        """根据ID规则获取合并文本时使用的连接符"""
        if unique_id and unique_id.startswith("ui_nm"):
            return "  "  # 对于 ui_nm 开头的ID，使用空格连接符
        else:
            return " \\n "  # 其他情况使用换行符

    def write_compact_xml(self, root: ET.Element, path: Path) -> bool:
        """使用 ElementTree 写入 XML 文件，并手动插入换行符以实现 <Table>\n<Row> 格式"""
        try:
            # 生成紧凑的 XML 字符串
            xml_string = ET.tostring(
                root, encoding="utf-8", short_empty_elements=False
            ).decode("utf-8")

            # 优化换行符插入逻辑
            replacements = [
                ("><Row>", ">\n<Row>"),
                ("</Row><Row>", "</Row>\n<Row>"),
                ("</Row></Table>", "</Row>\n</Table>"),
            ]

            for old, new in replacements:
                xml_string = xml_string.replace(old, new)

            # 确保输出目录存在
            path.parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(xml_string)

            return True
        except Exception as e:
            print(f"❌ 写入文件 {path} 时发生错误: {e}")
            return False

    def read_corrections_data(
        self, correction_dir: Path
    ) -> Tuple[Dict[str, str], Dict[str, ET.Element]]:
        """读取修正文件，返回 ID 到修正文本的映射和 ID 到完整 Row 元素的映射"""
        correction_map: Dict[str, str] = {}
        correction_rows: Dict[str, ET.Element] = {}

        try:
            xml_files = list(correction_dir.glob("*.xml"))
            if not xml_files:
                print(f"⚠️ 警告：修正目录中没有找到XML文件: {correction_dir}")
                return correction_map, correction_rows

            for correction_path in xml_files:
                print(f"尝试读取修正文件: {correction_path.name}")
                tree_corr = ET.parse(correction_path)
                root_corr = tree_corr.getroot()

                for row in root_corr.findall("Row"):
                    cells = row.findall("Cell")

                    if len(cells) >= 3:
                        unique_id = cells[0].text or ""
                        corrected_chinese = cells[2].text or ""

                        if unique_id:  # 只处理非空ID
                            correction_map[unique_id] = corrected_chinese
                            correction_rows[unique_id] = copy.deepcopy(row)

            print(f"✅ 已从修正文件读取 {len(correction_map)} 条修正记录。")
            return correction_map, correction_rows

        except ET.ParseError as e:
            print(f"❌ 错误：修正文件格式错误 ({e})")
        except Exception as e:
            print(f"❌ 错误：解析修正文件失败: {e}")

        return correction_map, correction_rows

    def process_single_file(
        self,
        original_file_path: Path,
        correction_map: Dict[str, str],
        correction_rows: Dict[str, ET.Element],
    ) -> Optional[Path]:
        """处理单个原始 XML 文件，应用修正，执行双语化"""
        original_filename = original_file_path.name
        output_xml_path = self.temp_dir / original_filename

        print(f"\n--- 正在处理原始文件: {original_filename} ---")

        try:
            tree_orig = ET.parse(original_file_path)
            root_orig = tree_orig.getroot()
        except Exception as e:
            print(f"❌ 错误：读取或解析原始文件 '{original_filename}' 失败: {e}")
            return None

        applied_count = 0
        total_rows = 0
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

                # 应用修正
                if unique_id and unique_id in correction_map:
                    final_chinese_text = correction_map[unique_id]
                    applied_count += 1

                    # 标记修正记录为已使用
                    if unique_id in correction_rows:
                        ids_to_delete.add(unique_id)

                # 双语化
                connector = self.get_connector(unique_id)
                combined_text = f"{final_chinese_text}{connector}{english_text}"
                chinese_cell.text = combined_text

        # 删除已使用的修正记录
        for unique_id in ids_to_delete:
            correction_rows.pop(unique_id, None)

        print(
            f"🔄 文件 '{original_filename}' 处理完毕。总记录 {total_rows} 条，应用修正 {applied_count} 条。"
        )

        # 写入双语化后的文件
        if self.write_compact_xml(root_orig, output_xml_path):
            print(f"🎉 双语文件保存至: {original_filename}")
            return output_xml_path
        else:
            return None

    def write_remaining_corrections(
        self, correction_rows: Dict[str, ET.Element]
    ) -> Optional[Path]:
        """将剩余未匹配的 Row 写入新的 XML 文件"""
        if not correction_rows:
            print("ℹ️ 修正文件中所有记录均已被原始文件使用，无需生成剩余修正文件。")
            return None

        print("\n--- 正在生成剩余修正文件 ---")

        root = ET.Element("Table")
        for row in correction_rows.values():
            root.append(row)

        output_path = self.temp_dir / "text__chinesesfixptf.xml"

        if self.write_compact_xml(root, output_path):
            print(
                f"➕ 已将修正文件中未使用的 {len(correction_rows)} 条记录保存为: text__chinesesfixptf.xml"
            )
            return output_path
        else:
            return None

    def create_pak_archive(
        self, files_to_package: List[Path], pak_output_path: Path
    ) -> bool:
        """将指定的 XML 文件列表压缩成单个 PAK 档案"""
        if not files_to_package:
            print("❌ 错误：没有文件需要打包。跳过 PAK 生成。")
            return False

        print(f"\n--- 开始执行 PAK 文件打包：{pak_output_path.name} ---")

        try:
            # 确保输出目录存在
            pak_output_path.parent.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(
                pak_output_path, "w", zipfile.ZIP_DEFLATED
            ) as pak_file:
                for file_path in files_to_package:
                    if not file_path.exists():
                        print(f"⚠️ 警告：文件 '{file_path}' 不存在，跳过打包。")
                        continue

                    internal_filename = file_path.name
                    pak_file.write(file_path, internal_filename)
                    print(f"📦 已打包: '{internal_filename}'")

            print(f"🎉 PAK 打包成功！文件保存至: {pak_output_path}")
            return True

        except Exception as e:
            print(f"❌ 错误：打包过程中发生异常: {e}")
            return False

    def cleanup_temp_files(self):
        """清理临时文件"""
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                print("🧹 已清理临时文件")
        except Exception as e:
            print(f"⚠️ 清理临时文件时出错: {e}")

    def backup_correction_file(self) -> bool:
        """备份修正文件"""
        try:
            if self.correction_pak_path.exists():
                shutil.copy2(self.correction_pak_path, self.correction_backup_path)
                print(f"📋 已备份修正文件: {self.correction_backup_path}")
                return True
            else:
                print("⚠️ 警告：修正文件不存在，无需备份")
                return True
        except Exception as e:
            print(f"❌ 备份修正文件失败: {e}")
            return False

    def get_correction_source(self) -> Path:
        """获取修正文件的来源路径（优先使用备份文件）"""
        if self.correction_backup_path.exists():
            print(f"📁 使用备份文件作为修正源: {self.correction_backup_path.name}")
            return self.correction_backup_path
        else:
            print(f"📁 使用当前修正文件作为修正源: {self.correction_pak_path.name}")
            return self.correction_pak_path

    def process_specific_files(self) -> bool:
        """执行特定文件的自动化处理流程"""
        print("🚀 开始天国拯救2特定文件自动化处理...")

        # 0. 备份修正文件（如果备份文件不存在）
        print("\n=== 步骤0: 备份修正文件 ===")
        if not self.correction_backup_path.exists():
            if not self.backup_correction_file():
                return False
        else:
            print("📋 备份文件已存在，跳过备份")

        # 1. 解压原始pak文件
        print("\n=== 步骤1: 解压原始pak文件 ===")
        if not self.extract_pak_file(self.original_pak_path, self.original_xml_dir):
            return False

        # 2. 解压修正pak文件（优先使用备份文件）
        print("\n=== 步骤2: 解压修正pak文件 ===")
        correction_source = self.get_correction_source()
        if not self.extract_pak_file(correction_source, self.correction_xml_dir):
            return False

        # 3. 读取修正数据
        print("\n=== 步骤3: 读取修正数据 ===")
        correction_map, correction_rows = self.read_corrections_data(
            self.correction_xml_dir
        )

        # 4. 只处理特定的原始文件：text_ui_dialog.xml
        print("\n=== 步骤4: 处理特定原始文件 ===")
        generated_xml_files: List[Path] = []

        # 只处理 text_ui_dialog.xml
        target_file = self.original_xml_dir / "text_ui_dialog.xml"
        if not target_file.exists():
            print(f"❌ 错误：目标文件不存在: {target_file}")
            return False

        merged_file_path = self.process_single_file(
            target_file, correction_map, correction_rows
        )
        if merged_file_path:
            generated_xml_files.append(merged_file_path)

        # 5. 处理修正文件：生成新的text__chinesesfixptf.xml
        print("\n=== 步骤5: 生成新的修正文件 ===")
        # 将剩余修正记录保存为新的text__chinesesfixptf.xml
        new_correction_path = self.write_remaining_corrections(correction_rows)
        if new_correction_path:
            generated_xml_files.append(new_correction_path)

        # 6. 创建新的pak文件（只包含指定的两个文件）
        print("\n=== 步骤6: 创建新的pak文件 ===")
        if generated_xml_files:
            # 确保只包含指定的两个文件
            final_files = []
            for file_path in generated_xml_files:
                if file_path.name in ["text_ui_dialog.xml", "text__chinesesfixptf.xml"]:
                    final_files.append(file_path)

            if len(final_files) == 2:
                if self.create_pak_archive(final_files, self.output_pak_path):
                    print(f"✅ 新的pak文件已成功替换到: {self.output_pak_path}")
                    print(
                        "📦 最终pak文件包含: text_ui_dialog.xml + text__chinesesfixptf.xml"
                    )
                else:
                    print("❌ 创建pak文件失败")
                    return False
            else:
                print(
                    f"❌ 错误：最终文件数量不正确，期望2个文件，实际{len(final_files)}个"
                )
                return False
        else:
            print("❌ 错误：没有生成任何文件，跳过打包。")
            return False

        # 7. 清理临时文件
        print("\n=== 步骤7: 清理临时文件 ===")
        self.cleanup_temp_files()

        print("\n🎉 特定文件自动化处理完成！")
        return True

    def process(self) -> bool:
        """执行完整的自动化处理流程（兼容旧版本）"""
        return self.process_specific_files()


def main():
    """主函数"""
    processor = AutoLocalizationProcessor()

    # 检查路径是否存在
    if not processor.original_pak_path.exists():
        print(f"❌ 错误：原始pak文件不存在: {processor.original_pak_path}")
        return

    if not processor.correction_pak_path.parent.exists():
        print(f"❌ 错误：修正目录不存在: {processor.correction_pak_path.parent}")
        return

    # 执行处理
    success = processor.process()

    if success:
        print("\n✅ 处理成功完成！")
    else:
        print("\n❌ 处理失败！")


if __name__ == "__main__":
    main()
