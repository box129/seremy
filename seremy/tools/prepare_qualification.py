"""Prepare fixed synthetic and real installed-library publications for renderer qualification."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from seremy.product import analyze, publish
from seremy.viewer import render_map
from build_render_fixture import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("library", type=Path)
    parser.add_argument("--refresh", action="store_true")
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if arguments.refresh:
        results = json.loads((output / "inputs.json").read_text(encoding="utf8"))
        for name, record in results.items():
            previous = Path(record["publication"])
            bundle = json.loads((previous / "graph.json").read_text(encoding="utf8"))
            ir = json.loads((previous / "document-ir.json").read_text(encoding="utf8"))
            checks = json.loads((previous / "validation.json").read_text(encoding="utf8"))
            markdown = (previous / "architecture.md").read_text(encoding="utf8")
            record.setdefault("uncached_publication", record["publication"])
            record["publication"] = str(publish(output / name, bundle, ir, markdown, checks, render_map(bundle)))
        (output / "inputs.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
        print(json.dumps(results))
        return
    results = {}
    with tempfile.TemporaryDirectory(prefix="seremy-qualification-") as scratch:
        for name in ("synthetic", "pydantic"):
            root = Path(scratch) / name
            root.mkdir()
            if name == "synthetic":
                generate(root)
            else:
                for source in arguments.library.rglob("*.py"):
                    target = root / source.relative_to(arguments.library)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            bundle, ir, markdown, checks = analyze(root, use_git=False,
                snapshot_identity={"repository_id": "qualification:" + name, "declared_root": "qualification:/" + name})
            publication = publish(output / name, bundle, ir, markdown, checks, render_map(bundle))
            sources = bundle["contents"]["source_texts"]
            results[name] = {"publication": str(publication), "content_digest": bundle["bundle"]["content_digest"],
                             "files": len(sources), "lines": sum(len(text.split("\n")) for text in sources.values()),
                             "source_sites": sum(len(edge["occurrences"]) for edge in bundle["contents"]["s03"]["artifact"]["edges"])}
    results["pydantic"]["source"] = str(arguments.library.resolve())
    distribution = next(distribution for distribution in importlib.metadata.distributions(path=[str(arguments.library.parent)])
                        if distribution.metadata["Name"].lower() == "pydantic")
    results["pydantic"]["version"] = distribution.version
    for name in distribution.files:
        if str(name).endswith("licenses/LICENSE"):
            shutil.copyfile(distribution.locate_file(name), output / "pydantic-LICENSE.txt")
    (output / "inputs.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
    print(json.dumps(results))


if __name__ == "__main__":
    main()
