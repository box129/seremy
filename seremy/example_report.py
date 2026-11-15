"""Prepare the bundled, public Redux example without a model request."""
from functools import lru_cache
import json
from pathlib import Path
import tempfile
import time

from seremy.product import analyze, publish
from seremy.viewer import render_map


@lru_cache(maxsize=1)
def example_report(refresh=False):
    prepared = Path(__file__).parent / "example-report.json"
    if prepared.exists() and not refresh:
        return json.loads(prepared.read_text(encoding="utf8"))
    fixture = Path(__file__).parent / "fixtures" / "redux-slice" / "src"
    bundle, document, markdown, checks = analyze(fixture, use_git=False,
        snapshot_identity={"repository_id": "bundled-redux-example", "declared_root": "redux/src"})
    with tempfile.TemporaryDirectory(prefix="seremy-example-") as directory:
        version = publish(Path(directory), bundle, document, markdown, checks, render_map(bundle))
        files = {name: (version / name).read_text(encoding="utf8") for name in
                 ("map.html", "architecture.md", "graph.json", "validation.json", "manifest.json")}
    return {"id": version.name, "name": "Redux example (bundled source)", "saved": int(time.time() * 1000), "files": files, "drafts": []}


if __name__ == "__main__":
    report = example_report(True)
    (Path(__file__).parent / "example-report.json").write_text(json.dumps(report), encoding="utf8")
