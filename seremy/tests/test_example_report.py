import hashlib
import json

from seremy.example_report import example_report


def test_prepared_example_has_checked_exports_and_real_action_source():
    report = example_report()
    assert len(report["id"]) == 64
    manifest = json.loads(report["files"]["manifest.json"])
    for name, text in report["files"].items():
        if name != "manifest.json":
            assert hashlib.sha256(text.encode("utf8")).hexdigest() == manifest["files"][name]
    assert "isAction" in report["files"]["map.html"]
    assert "isPlainObject" in report["files"]["architecture.md"]
    assert "generation_token" not in report
