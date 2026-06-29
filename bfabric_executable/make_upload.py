#!/usr/bin/env python3
"""Convert a B-Fabric web-GUI 'XML Export' executable into the clean shape that
``bfabric-cli executable upload`` accepts (it then CREATES a new executable).

Emits XML or YAML based on the output extension. The clean shape drops all XML
attributes (``classname``/``id`` -> xmltodict ``@classname`` -> SUDS crash), the
per-parameter ``<executable>`` back-references, every server-managed field, and
any id (``upload`` refuses an id and always creates a NEW executable).

Usage: python make_upload.py SRC.xml OUT.{xml,yaml}
"""
import sys
import xml.etree.ElementTree as ET

ROOT_KEEP = ["name", "description", "program", "context", "enabled"]
PARAM_KEEP = ["description", "context", "enumeration", "key", "label",
              "modifiable", "required", "type", "value"]


def to_dict(src: str) -> dict:
    """Parse the GUI-export XML into the clean ``{'executable': {...}}`` dict."""
    root = ET.parse(src).getroot()
    ex: dict = {}
    for tag in ROOT_KEEP:
        el = root.find(tag)
        if el is not None:
            ex[tag] = el.text
    params = []
    for p in root.findall("parameter"):
        d: dict = {}
        for tag in PARAM_KEEP:
            if tag == "enumeration":
                vals = [e.text for e in p.findall("enumeration")]
                if vals:
                    d["enumeration"] = vals
            else:
                el = p.find(tag)
                if el is not None:
                    d[tag] = el.text
        params.append(d)
    ex["parameter"] = params
    return {"executable": ex}


def write_yaml(data: dict, dst: str) -> None:
    import yaml
    with open(dst, "w") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False, allow_unicode=True, width=10**9)


def write_xml(data: dict, dst: str) -> None:
    ex = data["executable"]
    out = ET.Element("executable")
    for tag in ROOT_KEEP:
        if tag in ex:
            ET.SubElement(out, tag).text = ex[tag]
    for p in ex["parameter"]:
        np = ET.SubElement(out, "parameter")
        for tag in PARAM_KEEP:
            if tag == "enumeration":
                for v in p.get("enumeration", []):
                    ET.SubElement(np, "enumeration").text = v
            elif tag in p:
                ET.SubElement(np, tag).text = p[tag]
    ET.indent(out, space="  ")
    with open(dst, "w") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write(ET.tostring(out, encoding="unicode") + "\n")


def validate(path: str) -> None:
    """Mirror upload.py's pre-save checks so we fail locally, not mid-request."""
    if path.endswith((".yaml", ".yml")):
        import yaml
        data = yaml.safe_load(open(path))
    else:
        data = _parse_any_xml(path)
    assert set(data) == {"executable"}, f"top level must be exactly 'executable', got {list(data)}"
    ex = data["executable"]
    assert "id" not in ex, "upload refuses an 'id' (it always creates a NEW executable)"
    n = len(ex.get("parameter", []))
    assert n, "no parameters found"
    print(f"OK: {path} — single 'executable', no id, {n} parameters")


def _parse_any_xml(path: str) -> dict:
    root = ET.parse(path).getroot()
    assert not root.attrib, "clean XML must have no attributes on <executable>"
    return {"executable": {"parameter": root.findall("parameter"), **{c.tag: c.text for c in root if c.tag != "parameter"}}}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "validate":
        validate(sys.argv[2])
    else:
        src, dst = sys.argv[1], sys.argv[2]
        data = to_dict(src)
        (write_yaml if dst.endswith((".yaml", ".yml")) else write_xml)(data, dst)
        validate(dst)
