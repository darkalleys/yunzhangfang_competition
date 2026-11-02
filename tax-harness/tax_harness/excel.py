"""只读导入赛题 XLSX，使用标准库，不依赖 Excel 或第三方库。"""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def read_workbook(path):
    """返回 sheet -> [{列字母: 原始文本}]，忽略样式，不依赖公式缓存。"""
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        strings = []
        if "xl/sharedStrings.xml" in names:
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")):
                strings.append("".join(t.text or "" for t in item.iterfind(".//s:t", NS)))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        result = {}
        for sheet in workbook.findall("s:sheets/s:sheet", NS):
            target = targets[sheet.attrib[f"{{{REL}}}id"]]
            entry = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
            if ".." in PurePosixPath(entry).parts:
                raise ValueError("工作表路径无效")
            rows = []
            root = ET.fromstring(archive.read(entry))
            for row in root.findall("s:sheetData/s:row", NS):
                values = {}
                for cell in row.findall("s:c", NS):
                    col = "".join(c for c in cell.attrib["r"] if c.isalpha())
                    value = cell.findtext("s:v", default="", namespaces=NS)
                    kind = cell.attrib.get("t")
                    if kind == "s":
                        value = strings[int(value)]
                    elif kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iterfind(".//s:t", NS))
                    # 业务明细不能依赖未重新计算的公式值。
                    if cell.find("s:f", NS) is not None:
                        value = None
                    values[col] = value
                rows.append(values)
            result[sheet.attrib["name"]] = rows
        return result


def cents(raw):
    try:
        amount = Decimal(str(raw))
        if not amount.is_finite() or amount < 0 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError("金额必须是非负且最多两位小数")
        return int(amount * 100)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("金额格式无效") from exc


def iso_date(raw):
    if not raw:
        raise ValueError("缺少日期")
    if len(raw) >= 10 and raw[4:5] == "-":
        return date.fromisoformat(raw[:10]).isoformat()
    # 兼容采用标准 1900 日期系统存储的 Excel 日期序号。
    return (datetime(1899, 12, 30) + timedelta(days=float(raw))).date().isoformat()
