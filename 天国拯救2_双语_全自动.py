import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from localize_core import (
    create_pak_archive,
    ensure_clean_dir,
    extract_pak_file,
    process_xml_tree,
    read_corrections_data,
    write_compact_xml,
    write_remaining_corrections,
)


class AutoLocalizationProcessor:
    """天国拯救2本地化文件自动化处理器"""

    def __init__(
        self,
        steam_path: Optional[Path] = None,
        work_dir: Optional[Path] = None,
        target_files: Optional[List[str]] = None,
        use_backup_as_source: bool = False,
        keep_temp: bool = False,
    ):
        self.steam_path = steam_path or Path(
            "C:/Program Files (x86)/Steam/steamapps/common/KingdomComeDeliverance2"
        )
        self.original_pak_path = self.steam_path / "Localization/Chineses_xml.pak"
        self.correction_pak_path = (
            self.steam_path / "Mods/chinesesfixptf/Localization/Chineses_xml.pak"
        )
        self.correction_backup_path = self.correction_pak_path.with_suffix(".pak.backup")
        self.output_pak_path = self.correction_pak_path

        self.work_dir = work_dir or Path(__file__).parent
        self.temp_dir = self.work_dir / "temp_processing"
        self.original_xml_dir = self.temp_dir / "original_xml"
        self.correction_xml_dir = self.temp_dir / "correction_xml"

        self.target_files = target_files or ["text_ui_dialog.xml"]
        self.use_backup_as_source = use_backup_as_source
        self.keep_temp = keep_temp

    def prepare_temp_dirs(self) -> None:
        ensure_clean_dir(self.temp_dir)
        ensure_clean_dir(self.original_xml_dir)
        ensure_clean_dir(self.correction_xml_dir)

    def backup_correction_file(self) -> bool:
        try:
            if not self.correction_pak_path.exists():
                print("警告：修正文件不存在，无需备份")
                return True

            if self.correction_backup_path.exists():
                print(f"备份文件已存在: {self.correction_backup_path.name}")
                return True

            self.correction_backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.correction_pak_path, self.correction_backup_path)
            print(f"已备份修正文件: {self.correction_backup_path}")
            return True
        except Exception as exc:
            print(f"错误：备份修正文件失败: {exc}")
            return False

    def get_correction_source(self) -> Path:
        if self.use_backup_as_source:
            if not self.correction_backup_path.exists():
                raise FileNotFoundError(
                    f"指定使用备份文件，但文件不存在: {self.correction_backup_path}"
                )
            print(f"使用备份文件作为修正源: {self.correction_backup_path.name}")
            return self.correction_backup_path

        print(f"使用当前修正文件作为修正源: {self.correction_pak_path.name}")
        return self.correction_pak_path

    def read_corrections(
        self,
    ) -> tuple[Dict[str, str], Dict[str, ET.Element]]:
        xml_files = sorted(self.correction_xml_dir.glob("*.xml"))
        if not xml_files:
            print(f"警告：修正目录中没有找到XML文件: {self.correction_xml_dir}")
            return {}, {}

        correction_map, correction_rows, duplicate_sources = read_corrections_data(xml_files)

        if duplicate_sources:
            print(f"警告：检测到 {len(duplicate_sources)} 个重复ID，已采用最后一次出现的记录。")

        print(f"已从修正文件读取 {len(correction_map)} 条修正记录。")
        return correction_map, correction_rows

    def process_single_file(
        self,
        original_file_path: Path,
        correction_map: Dict[str, str],
        correction_rows: Dict[str, ET.Element],
    ) -> Optional[Path]:
        output_xml_path = self.temp_dir / original_file_path.name
        print(f"\n--- 正在处理原始文件: {original_file_path.name} ---")

        try:
            root_orig = ET.parse(original_file_path).getroot()
        except Exception as exc:
            print(f"错误：读取或解析原始文件失败: {original_file_path} ({exc})")
            return None

        stats = process_xml_tree(root_orig, correction_map, correction_rows)
        print(
            f"文件 '{original_file_path.name}' 处理完毕。总记录 {stats.total_rows} 条，"
            f"应用修正 {stats.corrected_rows} 条，跳过 {stats.skipped_rows} 条。"
        )

        try:
            write_compact_xml(root_orig, output_xml_path)
        except Exception as exc:
            print(f"错误：写入双语文件失败: {output_xml_path} ({exc})")
            return None

        print(f"双语文件保存至: {output_xml_path.name}")
        return output_xml_path

    def process_specific_files(self) -> bool:
        print("开始天国拯救2特定文件自动化处理...")

        print("\n=== 步骤0: 备份修正文件 ===")
        if not self.backup_correction_file():
            return False

        print("\n=== 步骤1: 准备临时目录 ===")
        self.prepare_temp_dirs()

        try:
            print("\n=== 步骤2: 解压原始pak文件 ===")
            extract_pak_file(self.original_pak_path, self.original_xml_dir)

            print("\n=== 步骤3: 解压修正pak文件 ===")
            extract_pak_file(self.get_correction_source(), self.correction_xml_dir)
        except Exception as exc:
            print(f"错误：解压失败: {exc}")
            if not self.keep_temp:
                self.cleanup_temp_files()
            return False

        print("\n=== 步骤4: 读取修正数据 ===")
        correction_map, correction_rows = self.read_corrections()

        print("\n=== 步骤5: 处理目标文件 ===")
        generated_xml_files: List[Path] = []
        missing_targets: List[str] = []
        for target_name in self.target_files:
            target_file = self.original_xml_dir / target_name
            if not target_file.exists():
                missing_targets.append(target_name)
                continue

            merged_file_path = self.process_single_file(
                target_file, correction_map, correction_rows
            )
            if merged_file_path:
                generated_xml_files.append(merged_file_path)

        if missing_targets:
            print(f"警告：以下目标文件不存在，已跳过: {', '.join(missing_targets)}")

        if not generated_xml_files:
            print("错误：没有生成任何双语文件。")
            if not self.keep_temp:
                self.cleanup_temp_files()
            return False

        print("\n=== 步骤6: 生成剩余修正文件 ===")
        correction_output = self.temp_dir / "text__chinesesfixptf.xml"
        if write_remaining_corrections(correction_rows, correction_output):
            generated_xml_files.append(correction_output)
            print(f"已生成剩余修正文件: {correction_output.name}")
        else:
            print("没有剩余修正记录，无需生成补充文件。")

        print("\n=== 步骤7: 创建新的pak文件 ===")
        try:
            written_files = create_pak_archive(generated_xml_files, self.output_pak_path)
        except Exception as exc:
            print(f"错误：创建pak文件失败: {exc}")
            if not self.keep_temp:
                self.cleanup_temp_files()
            return False

        print(
            "最终pak文件包含: "
            + ", ".join(file_path.name for file_path in written_files)
        )

        if not self.keep_temp:
            print("\n=== 步骤8: 清理临时文件 ===")
            self.cleanup_temp_files()

        print("\n特定文件自动化处理完成！")
        return True

    def cleanup_temp_files(self) -> None:
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                print("已清理临时文件")
        except Exception as exc:
            print(f"警告：清理临时文件时出错: {exc}")

    def process(self) -> bool:
        return self.process_specific_files()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="处理天国拯救2双语字幕pak文件")
    parser.add_argument(
        "--steam-path",
        type=Path,
        default=None,
        help="游戏根目录，默认使用脚本内置路径",
    )
    parser.add_argument(
        "--target-file",
        dest="target_files",
        action="append",
        default=None,
        help="要处理的原始XML文件名，可重复传入，默认仅 text_ui_dialog.xml",
    )
    parser.add_argument(
        "--use-backup-as-source",
        action="store_true",
        help="使用 .pak.backup 作为修正源，而不是当前 mod pak",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="保留 temp_processing 目录用于排查问题",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    processor = AutoLocalizationProcessor(
        steam_path=args.steam_path,
        target_files=args.target_files,
        use_backup_as_source=args.use_backup_as_source,
        keep_temp=args.keep_temp,
    )

    if not processor.original_pak_path.exists():
        print(f"错误：原始pak文件不存在: {processor.original_pak_path}")
        return 1

    if not processor.correction_pak_path.parent.exists():
        print(f"错误：修正目录不存在: {processor.correction_pak_path.parent}")
        return 1

    if not processor.correction_pak_path.exists() and not args.use_backup_as_source:
        print(f"错误：修正pak文件不存在: {processor.correction_pak_path}")
        return 1

    success = processor.process()
    if success:
        print("\n处理成功完成！")
        return 0

    print("\n处理失败！")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
