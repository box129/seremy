"""Rebuild the local TypeScript milestone slice and both consumer inputs."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
from seremy.contracts import SourceBlob, AnalysisTextBlob, sha256_hex
from seremy.discovery import discover
from seremy.parsing import run_adapter, build_parsed_results, artifact_digest
from seremy.resolver import Resolver
from seremy.bundle import build_bundle, BundleLoader
from seremy.documentation import build_document_ir, validate_document, render_markdown
from build_map import main as build_map

FILES = ["src/utils/isAction.ts", "src/utils/isPlainObject.ts"]


def main():
    source = ROOT / "fixtures/redux-slice"
    manifest = discover(source, repository_id="local:redux-slice")
    blobs = {}
    inventory = {r.file_id: r for r in manifest.eligible}
    for fid in FILES:
        data = (source / fid).read_bytes()
        if sha256_hex(data) != inventory[fid].content_sha256:
            raise ValueError("source changed during discovery: " + fid)
        blob = SourceBlob(file_id=fid, raw_path=None,
                          content_sha256=sha256_hex(data), byte_count=len(data), read_status="complete")
        blobs[fid] = (AnalysisTextBlob.from_source(blob, data), data)
    output = run_adapter(source, FILES)
    results = build_parsed_results(output, blobs)
    relations = Resolver(results, expected_s02_digest=artifact_digest(results)).resolve()
    bundle = build_bundle(manifest, results, relations)
    loader = BundleLoader(bundle)
    document = build_document_ir(loader)
    errors = validate_document(document, loader)
    if errors:
        raise ValueError(errors)
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    def write(name, value):
        (artifacts/name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")
    write("s02-parsed-slice.json", bundle["contents"]["s02"]["artifact"])
    write("s03-relations-slice.json", bundle["contents"]["s03"]["artifact"])
    write("graph-bundle-slice.json", bundle)
    write("s08-document-slice.json", document)
    (artifacts/"s08-document-slice.md").write_text(render_markdown(document), encoding="utf8")
    if build_map():
        raise RuntimeError("map build failed")
    print(json.dumps({"bundle":loader.meta["bundle_digest"],"edges":len(relations.edges),
                      "document_errors":errors,"profile":"typescript-checker-v0.2"}))


if __name__ == "__main__":
    main()

