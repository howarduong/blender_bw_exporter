"""XML text helpers for BigWorld DataSection-style files."""

from __future__ import annotations

import xml.etree.ElementTree as ET


def read_text(elem, default: str = "") -> str:
    if elem is None:
        return default
    if elem.text and elem.text.strip():
        return elem.text.strip()
    text_attr = elem.get("text")
    if text_attr:
        return text_attr.strip()
    return default


def sub_element(parent, tag: str, value: str = "") -> ET.Element:
    elem = ET.SubElement(parent, tag)
    if value:
        elem.text = f"\t{value}\t" if not value.startswith("\t") else value
    return elem
