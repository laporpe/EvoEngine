import tempfile
import unittest
import zipfile
from pathlib import Path

from sorghum_xlsx import column_index, read_nonempty_cells, read_table


WORKBOOK_XML = """<?xml version="1.0"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
 <sheets><sheet name="Data" sheetId="1" r:id="rId1"/><sheet name="Notes" sheetId="2" r:id="rId2"/></sheets>
</workbook>"""
RELS_XML = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="worksheet"/>
 <Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="worksheet"/>
</Relationships>"""
SHARED_XML = """<?xml version="1.0"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <si><t>Range</t></si><si><t>PlantTag</t></si><si><t>note</t></si>
</sst>"""
SHEET1_XML = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
 <row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>
 <row r="2"><c r="A2"><v>75</v></c><c r="C2"><v>1</v></c></row>
</sheetData></worksheet>"""
SHEET2_XML = """<?xml version="1.0"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
 <row r="1"><c r="A1" t="s"><v>2</v></c></row>
</sheetData></worksheet>"""


class XlsxReaderTests(unittest.TestCase):
    def test_column_index(self) -> None:
        self.assertEqual((0, 25, 26, 52), tuple(map(column_index, ("A1", "Z9", "AA2", "BA3"))))

    def test_reads_sparse_shared_string_table_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/workbook.xml", WORKBOOK_XML)
                archive.writestr("xl/_rels/workbook.xml.rels", RELS_XML)
                archive.writestr("xl/sharedStrings.xml", SHARED_XML)
                archive.writestr("xl/worksheets/sheet1.xml", SHEET1_XML)
                archive.writestr("xl/worksheets/sheet2.xml", SHEET2_XML)
            row = read_table(path, "Data")[0]
            self.assertEqual({"Range": 75, "PlantTag": 1}, row.values)
            self.assertEqual("C2", row.cells["PlantTag"].coordinate)
            self.assertEqual("note", read_nonempty_cells(path, "Notes")[0].value)


if __name__ == "__main__":
    unittest.main()
