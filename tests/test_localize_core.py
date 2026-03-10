import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from localize_core import (
    build_bilingual_text,
    create_pak_archive,
    ensure_clean_dir,
    process_xml_tree,
    split_bilingual_text,
    write_remaining_corrections,
)


def load_processor_module():
    module_path = Path(__file__).resolve().parent.parent / "天国拯救2_双语_全自动.py"
    spec = importlib.util.spec_from_file_location("auto_localization_processor", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LocalizeCoreTests(unittest.TestCase):
    def test_split_bilingual_text_supports_real_and_literal_newline(self):
        self.assertEqual(split_bilingual_text("中文\nEnglish"), ("中文", "English"))
        self.assertEqual(split_bilingual_text("中文 \\n English"), ("中文", "English"))

    def test_process_xml_tree_merges_rows_and_removes_used_corrections(self):
        root = ET.fromstring(
            "<Table><Row><Cell>id_1</Cell><Cell>Hello</Cell><Cell>你好</Cell></Row></Table>"
        )
        correction_rows = {
            "id_1": ET.fromstring(
                "<Row><Cell>id_1</Cell><Cell>Hello</Cell><Cell>修正</Cell></Row>"
            )
        }
        stats = process_xml_tree(root, {"id_1": "修正"}, correction_rows)

        self.assertEqual(stats.total_rows, 1)
        self.assertEqual(stats.corrected_rows, 1)
        self.assertEqual(root.find("Row/Cell[3]").text, build_bilingual_text("修正", "Hello", "id_1"))
        self.assertEqual(correction_rows, {})

    def test_write_remaining_corrections_returns_false_when_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "text__chinesesfixptf.xml"
            self.assertFalse(write_remaining_corrections({}, output_path))
            self.assertFalse(output_path.exists())

    def test_create_pak_archive_allows_single_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_file = base / "text_ui_dialog.xml"
            source_file.write_text("<Table />", encoding="utf-8")
            output_pak = base / "Chineses_xml.pak"

            written_files = create_pak_archive([source_file], output_pak)

            self.assertEqual(written_files, [source_file])
            with zipfile.ZipFile(output_pak, "r") as pak_file:
                self.assertEqual(pak_file.namelist(), ["text_ui_dialog.xml"])


class AutoLocalizationProcessorTests(unittest.TestCase):
    def test_prepare_temp_dirs_cleans_stale_files(self):
        module = load_processor_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            processor = module.AutoLocalizationProcessor(work_dir=Path(temp_dir))
            stale_file = processor.original_xml_dir / "stale.xml"
            stale_file.parent.mkdir(parents=True, exist_ok=True)
            stale_file.write_text("stale", encoding="utf-8")

            processor.prepare_temp_dirs()

            self.assertTrue(processor.original_xml_dir.exists())
            self.assertFalse(stale_file.exists())

    def test_default_source_prefers_current_correction_pak(self):
        module = load_processor_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_path = Path(temp_dir) / "steam"
            correction_dir = steam_path / "Mods/chinesesfixptf/Localization"
            correction_dir.mkdir(parents=True, exist_ok=True)
            current_pak = correction_dir / "Chineses_xml.pak"
            backup_pak = correction_dir / "Chineses_xml.pak.backup"
            current_pak.write_text("current", encoding="utf-8")
            backup_pak.write_text("backup", encoding="utf-8")

            processor = module.AutoLocalizationProcessor(steam_path=steam_path)

            self.assertEqual(processor.get_correction_source(), current_pak)


if __name__ == "__main__":
    unittest.main()
