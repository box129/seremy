"""Build a portable Pixi comparison page using the product's layout and byte mapping."""
import argparse
import json
from pathlib import Path
import re


def build(publication, output):
    tools = Path(__file__).resolve().parent
    template = (tools.parent / "map/product-template.html").read_text(encoding="utf8")
    html = (publication / "map.html").read_text(encoding="utf8")
    fixture = re.search(r'<script id="fixture" type="application/json">(.*?)</script>', html, re.S).group(1)
    layout = template[template.index("const folders=Object.create(null)"):template.index("layout();\nlet camera=")]
    positions = template[template.index("function position(span)"):template.index("function save(){")]
    prototype = (tools / "renderer-prototype.html").read_text(encoding="utf8")
    pixi = (tools / "node_modules/pixi.js/dist/pixi.min.js").read_text(encoding="utf8")
    prototype = prototype.replace("PIXI_BUNDLE", pixi)
    prototype = prototype.replace("FIXTURE_JSON", fixture).replace("SHARED_LAYOUT", layout).replace("SHARED_POSITIONS", positions)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prototype, encoding="utf8")
    print(json.dumps({"prototype": str(output), "files": len(json.loads(fixture)["files"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publication", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    build(arguments.publication, arguments.output)
