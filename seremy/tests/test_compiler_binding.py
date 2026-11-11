"""Independent semantic regressions for the compiler-backed binding profile."""
import json
from seremy.tests.test_resolver import _resolver_for
from seremy.resolver import MISSING, RESOLVED_SINGLE, UNSUPPORTED


def resolve(tmp_path, sources):
    for name, text in sources.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf8"))
    return _resolver_for(tmp_path, list(sources)).resolve()


def calls(result):
    return [r for r in result.resolutions if r.candidate_kind == "call"]


def test_default_import_cannot_bind_private_function(tmp_path):
    result = resolve(tmp_path, {
        "main.ts": "import chosen from './target'; export function entry(){ return chosen() }",
        "target.ts": "function hidden(){ return 1 } export const value = 2"
    })
    assert calls(result)[0].outcome == MISSING
    assert result.edges == []


def test_parameter_shadows_top_level_function(tmp_path):
    result = resolve(tmp_path, {"main.ts":
        "function chosen(){ return 1 } export function entry(chosen: () => number){ return chosen() }"})
    assert calls(result)[0].outcome == UNSUPPORTED
    assert calls(result)[0].reason == "callable_value_target_not_established"
    assert result.edges == []


def test_renamed_import_binds_exported_symbol(tmp_path):
    result = resolve(tmp_path, {
        "main.ts": "import {original as chosen} from './target'; export function entry(){ return chosen() }",
        "target.ts": "export function original(){ return 1 }"
    })
    record = calls(result)[0]
    assert record.outcome == RESOLVED_SINGLE
    assert record.target == "ent:target.ts#function_declaration:original@16"
    assert len(result.edges) == 1


def test_actual_default_export_selected_among_private_functions(tmp_path):
    result = resolve(tmp_path, {
        "main.ts": "import chosen from './target'; export function entry(){ return chosen() }",
        "target.ts": "function hidden(){} export default function actual(){ return 1 }"
    })
    assert calls(result)[0].outcome == RESOLVED_SINGLE
    assert ":actual@" in calls(result)[0].target


def test_reexport_alias_resolves_original_declaration(tmp_path):
    result = resolve(tmp_path, {
        "main.ts": "import {forwarded} from './barrel'; export function entry(){ return forwarded() }",
        "barrel.ts": "export {original as forwarded} from './target'",
        "target.ts": "export function original(){ return 1 }"
    })
    assert calls(result)[0].target == "ent:target.ts#function_declaration:original@16"


def test_tsconfig_path_alias(tmp_path):
    (tmp_path / "tsconfig.json").write_text(json.dumps({
        "compilerOptions": {"baseUrl": ".", "paths":{"@target":["target.ts"]}}}))
    result = resolve(tmp_path, {
        "main.ts": "import {original} from '@target'; export function entry(){ return original() }",
        "target.ts": "export function original(){ return 1 }"
    })
    assert calls(result)[0].target == "ent:target.ts#function_declaration:original@16"


def test_overload_signature_resolves_implementation(tmp_path):
    result = resolve(tmp_path, {"main.ts":
        "function chosen(x:string):string; function chosen(x:any){return x} "
        "export function entry(){return chosen('ok')}"})
    assert calls(result)[0].outcome == RESOLVED_SINGLE
    assert calls(result)[0].target.endswith("@43")


def test_bom_and_nonascii_preserve_raw_source_offsets(tmp_path):
    text = "\ufeff// é 🦊\r\nexport function chosen() {return 1}\r\nexport function entry(){return chosen()}"
    result = resolve(tmp_path, {"main.ts":text})
    record = calls(result)[0]
    assert record.outcome == RESOLVED_SINGLE
    assert record.candidate_span.start == text.encode().rindex(b"chosen")
    assert record.target.endswith("@"+str(text.encode().index(b"chosen")))


def test_unselected_disk_file_does_not_leak_into_snapshot(tmp_path):
    (tmp_path / "target.ts").write_text("export function original(){}")
    result = resolve(tmp_path, {"main.ts":
        "import {original} from './target'; export function entry(){return original()}"})
    assert calls(result)[0].outcome == MISSING
    assert result.edges == []


def test_ambient_function_does_not_crash_or_emit_runtime_edge(tmp_path):
    result = resolve(tmp_path, {"main.ts":
        "declare function chosen():number; export function entry(){return chosen()}"})
    assert calls(result)[0].outcome == UNSUPPORTED
    assert result.edges == []


def test_config_changes_invalidate_existing_binding(tmp_path):
    import shutil
    from seremy.tests.test_bundle import FIXTURE_ROOT
    from seremy.tests.test_bundle import _real_bundle
    from seremy.bundle import BundleLoader
    from seremy.staleness import check_staleness, citation_is_current
    loader = BundleLoader(_real_bundle())
    shutil.copytree(FIXTURE_ROOT, tmp_path, dirs_exist_ok=True)
    assert not check_staleness(loader, tmp_path)['stale']
    assert citation_is_current(loader, tmp_path, 'src/utils/isAction.ts', (185, 198))
    (tmp_path / 'tsconfig.json').write_text('{"compilerOptions":{"strict":false}}')
    assert check_staleness(loader, tmp_path)['config_changed']
    assert not citation_is_current(loader, tmp_path, 'src/utils/isAction.ts', (185, 198))
