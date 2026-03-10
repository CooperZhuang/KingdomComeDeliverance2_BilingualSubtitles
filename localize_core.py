from __future__ import annotations

import copy
import shutil
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROW_TAG = "Row"
CELL_TAG = "Cell"
DEFAULT_CONNECTOR = " \\n "
NAME_CONNECTOR = "  "


@dataclass
class ProcessingStats:
    total_rows: int = 0
    merged_rows: int = 0
    corrected_rows: int = 0
    skipped_rows: int = 0


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def extract_pak_file(pak_path: Path, extract_dir: Path) -> None:
    if not pak_path.exists():
        raise FileNotFoundError(f"pak file not found: {pak_path}")

    ensure_clean_dir(extract_dir)
    with zipfile.ZipFile(pak_path, "r") as pak_file:
        pak_file.extractall(extract_dir)


def get_connector(unique_id: Optional[str]) -> str:
    if unique_id and unique_id.startswith("ui_nm"):
        return NAME_CONNECTOR
    return DEFAULT_CONNECTOR


def write_compact_xml(root: ET.Element, path: Path) -> None:
    xml_string = ET.tostring(root, encoding="utf-8", short_empty_elements=False).decode(
        "utf-8"
    )
    replacements = [
        ("><Row>", ">\n<Row>"),
        ("</Row><Row>", "</Row>\n<Row>"),
        ("</Row></Table>", "</Row>\n</Table>"),
    ]
    for old, new in replacements:
        xml_string = xml_string.replace(old, new)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml_string, encoding="utf-8")


def build_bilingual_text(chinese_text: str, english_text: str, unique_id: str = "") -> str:
    return f"{chinese_text}{get_connector(unique_id)}{english_text}"


def split_bilingual_text(combined_text: str) -> Optional[Tuple[str, str]]:
    for delimiter in ("\n", "\\n"):
        if delimiter in combined_text:
            chinese_text, english_text = combined_text.split(delimiter, 1)
            return chinese_text.strip(), english_text.strip()
    return None


def load_xml_root(xml_path: Path) -> ET.Element:
    return ET.parse(xml_path).getroot()


def iter_rows(root: ET.Element) -> Iterable[ET.Element]:
    return root.findall(ROW_TAG)


def read_corrections_data(
    correction_paths: Sequence[Path],
) -> Tuple[Dict[str, str], Dict[str, ET.Element], Dict[str, List[Path]]]:
    correction_map: Dict[str, str] = {}
    correction_rows: Dict[str, ET.Element] = {}
    duplicate_sources: Dict[str, List[Path]] = {}

    for correction_path in correction_paths:
        root_corr = load_xml_root(correction_path)

        for row in iter_rows(root_corr):
            cells = row.findall(CELL_TAG)
            if len(cells) < 3:
                continue

            unique_id = cells[0].text or ""
            corrected_chinese = cells[2].text or ""
            if not unique_id:
                continue

            if unique_id in correction_map:
                duplicate_sources.setdefault(unique_id, []).append(correction_path)

            correction_map[unique_id] = corrected_chinese
            correction_rows[unique_id] = copy.deepcopy(row)

    return correction_map, correction_rows, duplicate_sources


def process_xml_tree(
    root_orig: ET.Element,
    correction_map: Dict[str, str],
    correction_rows: Optional[Dict[str, ET.Element]] = None,
) -> ProcessingStats:
    stats = ProcessingStats()
    ids_to_delete = set()

    for row in iter_rows(root_orig):
        stats.total_rows += 1
        cells = row.findall(CELL_TAG)
        if len(cells) < 3:
            stats.skipped_rows += 1
            continue

        unique_id = cells[0].text or ""
        english_text = cells[1].text or ""
        original_chinese = cells[2].text or ""
        final_chinese = correction_map.get(unique_id, original_chinese)

        if unique_id in correction_map:
            stats.corrected_rows += 1
            if correction_rows is not None and unique_id in correction_rows:
                ids_to_delete.add(unique_id)

        cells[2].text = build_bilingual_text(final_chinese, english_text, unique_id)
        stats.merged_rows += 1

    if correction_rows is not None:
        for unique_id in ids_to_delete:
            correction_rows.pop(unique_id, None)

    return stats


def write_remaining_corrections(correction_rows: Dict[str, ET.Element], output_path: Path) -> bool:
    if not correction_rows:
        return False

    root = ET.Element("Table")
    for row in correction_rows.values():
        root.append(copy.deepcopy(row))

    write_compact_xml(root, output_path)
    return True


def create_pak_archive(files_to_package: Sequence[Path], pak_output_path: Path) -> List[Path]:
    written_files: List[Path] = []
    pak_output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(pak_output_path, "w", zipfile.ZIP_DEFLATED) as pak_file:
        for file_path in files_to_package:
            if not file_path.exists():
                continue
            pak_file.write(file_path, file_path.name)
            written_files.append(file_path)

    return written_files
