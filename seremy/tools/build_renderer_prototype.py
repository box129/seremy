"""Build a portable Pixi comparison page using the product's layout and byte mapping."""
import argparse
import json
from pathlib import Path
import re


def build(publication, output):
    tools = Path(__file__).resolve().parent
    html = (publication / "map.html").read_text(encoding="utf8")
    fixture = re.search(r'<script id="fixture" type="application/json">(.*?)</script>', html, re.S).group(1)
    model = (tools.parent / "map/scene-model.js").read_text(encoding="utf8")
    prototype = (tools / "renderer-prototype.html").read_text(encoding="utf8")
    pixi = (tools / "node_modules/pixi.js/dist/pixi.min.js").read_text(encoding="utf8")
    prototype = prototype.replace("PIXI_BUNDLE", pixi)
    prototype = prototype.replace("FIXTURE_JSON", fixture).replace("SHARED_LAYOUT", model).replace("SHARED_POSITIONS", "")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prototype, encoding="utf8")
    print(json.dumps({"prototype": str(output), "files": len(json.loads(fixture)["files"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publication", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    build(arguments.publication, arguments.output)
