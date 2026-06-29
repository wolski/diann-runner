#!/usr/bin/env python3
"""Convert a B-Fabric web-GUI 'XML Export' executable into the clean shape that
``bfabric-cli executable upload`` accepts (which then CREATES a new executable).

The GUI export has ``<executable classname=.. id=..>`` plus per-parameter
``<executable .../>`` back-references; xmltodict turns those attributes into
``@classname``/``@id`` keys and the SUDS marshaller dies on them. ``upload`` also
rejects any ``id`` and always creates a NEW executable. So this strips all
attributes, the parameter back-references, every server-managed field, and any
id — leaving only the definition fields.

Usage: python make_upload_xml.py [IN.xml] [OUT.xml]
       (defaults: executable_A386_DIANN_3.2.xml -> executable_A386_DIANN_3.2.upload.xml)
"""
import sys
import xml.etree.ElementTree as ET

ROOT_KEEP = ["name", "description", "program", "context", "enabled"]
PARAM_KEEP = ["description", "context", "enumeration", "key", "label",
              "modifiable", "required", "type", "value"]


def convert(src: str, dst: str) -> None:
    root = ET.parse(src).getroot()
    out = ET.Element("executable")  # no attributes, no <id> -> upload creates new
    for tag in ROOT_KEEP:
        el = root.find(tag)
        if el is not None:
            ET.SubElement(out, tag).text = el.text
    for p in root.findall("parameter"):
        np = ET.SubElement(out, "parameter")
        for tag in PARAM_KEEP:
            if tag == "enumeration":
                for e in p.findall("enumeration"):
                    ET.SubElement(np, "enumeration").text = e.text
            else:
                el = p.find(tag)
                if el is not None:
                    ET.SubElement(np, tag).text = el.text
    ET.indent(out, space="  ")
    with open(dst, "w") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write(ET.tostring(out, encoding="unicode") + "\n")

    # guardrails: the exact things that break `upload`
    chk = ET.parse(dst).getroot()
    assert chk.findtext("id") is None, "upload rejects a top-level <id>"
    assert not chk.findall(".//parameter/executable"), "parameter back-references must be gone"
    def no_attrs(e): return (not e.attrib) and all(no_attrs(k) for k in e)
    assert no_attrs(chk), "no XML attributes allowed (xmltodict would emit @-keys)"
    print(f"{dst}: {len(chk.findall('parameter'))} parameters, clean (no attrs/id/back-refs)")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "executable_A386_DIANN_3.2.xml"
    dst = sys.argv[2] if len(sys.argv) > 2 else "executable_A386_DIANN_3.2.upload.xml"
    convert(src, dst)
