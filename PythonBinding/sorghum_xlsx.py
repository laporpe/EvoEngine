"""Small read-only XLSX table reader used by reproducible sorghum imports."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class SourceCell:
    coordinate: str
    value: object


@dataclass(frozen=True)
class SourceRow:
    row_number: int
    values: dict[str, object]
    cells: dict[str, SourceCell]


def column_index(coordinate: str) -> int:
    letters = re.match(r"[A-Z]+", coordinate.upper())
    if not letters:
        raise ValueError(f"invalid cell coordinate: {coordinate}")
    result = 0
    for letter in letters.group():
        result = result * 26 + ord(letter) - ord("A") + 1
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _sheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        item.attrib["Id"]: item.attrib["Target"]
        for item in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    result = {}
    sheets = workbook.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        return result
    for sheet in sheets:
        relationship_id = sheet.attrib[f"{{{DOC_REL_NS}}}id"]
        target = PurePosixPath(targets[relationship_id])
        result[sheet.attrib["name"]] = str(
            target if target.is_absolute() else PurePosixPath("xl") / target
        ).lstrip("/")
    return result


def _cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> object:
    cell_type = cell.attrib.get("t", "n")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    value = cell.find(f"{{{MAIN_NS}}}v")
    if value is None or value.text is None:
        return None
    text = value.text
    if cell_type == "s":
        return shared_strings[int(text)]
    if cell_type == "b":
        return text == "1"
    if cell_type in {"str", "e"}:
        return text
    number = float(text)
    return int(number) if number.is_integer() else number


def read_sheet(path: Path, sheet_name: str = "Sheet1") -> list[dict[int, SourceCell]]:
    with zipfile.ZipFile(path) as archive:
        sheet_paths = _sheet_paths(archive)
        if sheet_name not in sheet_paths:
            raise ValueError(f"{path.name} has no worksheet named {sheet_name}")
        shared_strings = _shared_strings(archive)
        root = ElementTree.fromstring(archive.read(sheet_paths[sheet_name]))
    rows: list[dict[int, SourceCell]] = []
    sheet_data = root.find(f"{{{MAIN_NS}}}sheetData")
    if sheet_data is None:
        return rows
    for row in sheet_data:
        row_cells = {}
        for cell in row.findall(f"{{{MAIN_NS}}}c"):
            coordinate = cell.attrib["r"]
            row_cells[column_index(coordinate)] = SourceCell(
                coordinate, _cell_value(cell, shared_strings)
            )
        rows.append(row_cells)
    return rows


def read_table(path: Path, sheet_name: str = "Sheet1") -> list[SourceRow]:
    rows = read_sheet(path, sheet_name)
    if not rows:
        return []
    headers = {
        index: str(cell.value).strip()
        for index, cell in rows[0].items()
        if cell.value not in (None, "")
    }
    result = []
    for row_number, row in enumerate(rows[1:], 2):
        values = {header: row[index].value if index in row else None for index, header in headers.items()}
        cells = {header: row[index] for index, header in headers.items() if index in row}
        result.append(SourceRow(row_number, values, cells))
    return result


def read_nonempty_cells(path: Path, sheet_name: str) -> list[SourceCell]:
    return [
        cell
        for row in read_sheet(path, sheet_name)
        for cell in row.values()
        if cell.value not in (None, "")
    ]
