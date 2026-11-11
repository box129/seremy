"""End-to-end regressions for the independently reproduced review findings."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import zipfile

import pytest

from seremy.__main__ import input_root, main
from seremy.architecture import aggregate
from seremy.bundle import BundleLoader
from seremy.contracts import canonical_bytes, sha256_hex
from seremy.documentation import validate_document
from seremy.product import analyze, publish, seal, validate_graph
from seremy.snapshot import collect_snapshot
from seremy.viewer import render_map


def write_sources(root, sources):
    for name, text in sources.items():
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(text.encode())
    return root


def test_git_input_cannot_launch_configured_monitor(tmp_path, monkeypatch):
    root=write_sources(tmp_path/'repo',{'main.py':'def main(): pass\n'})
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(root),'add','main.py'],check=True,capture_output=True)
    hook=tmp_path/'monitor.py'
    marker=tmp_path/'monitor-ran'
    hook.write_text('from pathlib import Path\nPath(__file__).with_name("monitor-ran").write_text("called")\n')
    monitor=f'"{Path(sys.executable).as_posix()}" "{hook.as_posix()}"'
    subprocess.run(['git','-C',str(root),'config','core.fsmonitor',monitor],check=True,capture_output=True)
    monkeypatch.setenv('GIT_CONFIG_COUNT','1')
    monkeypatch.setenv('GIT_CONFIG_KEY_0','core.fsmonitor')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0',monitor)
    _, sources, scope=collect_snapshot(root)
    assert scope['mode']=='git_tracked_and_nonignored'
    assert set(sources)=={'main.py'}
    assert not marker.exists()


def test_zip_ignores_git_metadata_and_uses_plain_scope(tmp_path):
    archive=tmp_path/'input.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('repo/main.py','def main(): pass\n')
        z.writestr('repo/.git/config','[core]\nfsmonitor = git version\n')
        z.writestr('repo/.git/HEAD','ref: refs/heads/main\n')
    args=SimpleNamespace(zip=archive,git_url=None)
    with input_root(args) as root:
        assert not (root/'.git').exists()
        bundle,*_=analyze(root,snapshot_identity=args.snapshot_identity,use_git=args.use_git)
        assert bundle['contents']['scope']['mode']=='plain_explicit_exclusions'
        assert bundle['contents']['snapshot']['repository_id'].startswith('zip:sha256:')


def test_multiple_imports_have_distinct_exact_candidates(tmp_path):
    bundle,*_=analyze(write_sources(tmp_path,{'main.py':'import math, os as operating\n'}))
    c=bundle['contents']
    records=c['s03']['artifact']['resolutions']
    assert len(records)==len({r['candidate_id'] for r in records})==2
    candidates=c['s02']['artifact']['files'][0]['candidates']
    assert [x['name'] for x in candidates]==['math','os as operating']
    assert {x['module_path'] for x in candidates}=={'math','os'}


def test_anonymous_default_is_explicitly_unsupported(tmp_path):
    bundle,*_=analyze(write_sources(tmp_path,{
        'a.ts':'export default function() {return 7;}\n',
        'b.ts':"import compute from './a'; export function caller(){return compute();}\n"}))
    c=bundle['contents']['s03']['artifact']
    assert not c['edges']
    call=next(r for r in c['resolutions'] if r['name']=='compute' and r['candidate_kind']=='call')
    assert call['outcome']=='UNSUPPORTED'
    assert call['reason']=='anonymous_function_identity_not_supported'


@pytest.mark.parametrize('route', ['direct','specifier','reexport'])
def test_type_only_aliases_never_become_runtime_edges(tmp_path, route):
    sources={'a.ts':'export function compute(){return 7;}\n'}
    if route=='reexport':
        sources['middle.ts']="export type {compute} from './a';\n"
        statement="import {compute} from './middle';"
    else:
        statement="import type {compute} from './a';" if route=='direct' else "import {type compute} from './a';"
    sources['b.ts']=statement+'export function caller(){return compute();}\n'
    bundle,*_=analyze(write_sources(tmp_path,sources))
    c=bundle['contents']['s03']['artifact']
    assert not c['edges']
    call=next(r for r in c['resolutions'] if r['candidate_kind']=='call')
    assert call['outcome']=='UNSUPPORTED'
    assert call['reason']=='type_only_alias_has_no_runtime_value'


@pytest.mark.parametrize('pattern', ["{'handler': handler}", '[*handler]', '{**handler}', 'handler'])
def test_pattern_capture_never_resolves_to_global_function(tmp_path, pattern):
    text=f'def handler(): pass\ndef run(value):\n match value:\n  case {pattern}:\n   return handler()\n'
    bundle,*_=analyze(write_sources(tmp_path,{'main.py':text}))
    c=bundle['contents']['s03']['artifact']
    assert not c['edges']
    assert c['resolutions'][0]['outcome']=='UNSUPPORTED'


def test_file_origin_calls_publish_and_enforce_directory_policy(tmp_path):
    write_sources(tmp_path,{'api/start.py':'from core.service import run\nrun()\n',
                            'core/service.py':'def run(): pass\n','core/__init__.py':''})
    bundle,_,markdown,_=analyze(tmp_path)
    c=bundle['contents']
    assert 'file:api/start.py' in markdown
    edge=c['s06']['artifact']['view']['edges'][0]
    assert (edge['source'],edge['target'])==('directory:api','directory:core')
    assert edge['source'] in c['s05']['artifact']['views'][0]['groups']
    assert not c['s06']['artifact']['view']['unassigned_edge_ids']
    with pytest.raises(ValueError,match='forbidden boundary'):
        analyze(tmp_path,policy={'forbidden':[{'source':'directory:api','target':'directory:core','kind':'CALLS'}]})


def test_failed_and_skipped_source_counts_are_visible_and_checked(tmp_path):
    write_sources(tmp_path,{'bad.py':'def broken(:\n','large.py':'#'*(1024*1024+1),
                            'package.json':'{"name":"example"}'})
    bundle,ir,markdown,report=analyze(tmp_path)
    assert '0 complete, 0 partial, 1 failed, 1 unprocessed of 2 source files' in markdown
    assert report['coverage']['s02']['source_file_count']==2
    forged=copy.deepcopy(ir)
    forged['label']['slice_scope']='2 of 2 source files parsed'
    assert any('coverage label' in e for e in validate_document(forged,BundleLoader(bundle)))
    wrong_counts=copy.deepcopy(bundle['contents'])
    wrong_counts['coverage']['s02']['complete']=2
    assert any('parsing coverage' in e for e in validate_graph(BundleLoader(seal(wrong_counts))))
    # Old saved bundles predate the added convenience coverage counters.
    old=copy.deepcopy(bundle['contents'])
    old['coverage']['s02'].pop('source_file_count')
    old['coverage']['s02'].pop('not_processed')
    from seremy.documentation import build_document_ir
    assert build_document_ir(BundleLoader(seal(old)))['label']==ir['label']


def test_frameworks_respect_ecosystem_and_collocated_manifests(tmp_path):
    bundle,*_=analyze(write_sources(tmp_path,{
        'package.json':'{"dependencies":{"react":"19","flask":"1"}}',
        'pyproject.toml':'[project]\ndependencies=["Flask>=3", "react>=1"]\n',
        'main.ts':"import React from 'react'; export function main(){return 1;}\n",
        'app.py':'from flask import Flask\ndef app(): pass\n'}))
    c=bundle['contents']
    frameworks=c['s04']['artifact']
    assert {(f['framework'],f['ecosystem']) for f in frameworks['frameworks']}=={('React','npm'),('Flask','python')}
    assert len(frameworks['packages'])==2
    assert len({p['package_id'] for p in frameworks['packages']})==2
    view=c['s05']['artifact']['views'][1]
    assert len(view['groups'])==2


@pytest.mark.parametrize('target',['structural_directory','deployable_package'])
def test_resealed_incorrect_membership_is_rejected(tmp_path,target):
    bundle,*_=analyze(write_sources(tmp_path,{'main.py':'def helper(): pass\ndef caller(): helper()\n',
                                             'pyproject.toml':'[project]\ndependencies=[]\n'}))
    c=copy.deepcopy(bundle['contents'])
    view=next(v for v in c['s05']['artifact']['views'] if v['target']==target)
    view['membership']={key:'invented-group' for key in view['membership']}
    view['groups']=['invented-group']
    view['version']=sha256_hex(canonical_bytes(view['membership']))
    c['s06']['artifact']['view']=aggregate(c['s03']['artifact']['edges'],c['s05']['artifact']['views'][0])
    for stage in ['s05','s06']:
        c[stage]['digest']=sha256_hex(canonical_bytes(c[stage]['artifact']))
    assert any('component membership' in e for e in validate_graph(BundleLoader(seal(c))))


def test_republication_rejects_corrupt_manifest_and_retains_pointer(tmp_path):
    root=write_sources(tmp_path/'source',{'main.py':'def main(): pass\n'})
    bundle,ir,markdown,report=analyze(root)
    output=tmp_path/'out'
    html=render_map(bundle)
    version=publish(output,bundle,ir,markdown,report,html)
    pointer=(output/'current.json').read_bytes()
    manifest=json.loads((version/'manifest.json').read_bytes())
    manifest['acceptance']='accepted'
    (version/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='manifest is corrupt'):
        publish(output,bundle,ir,markdown,report,html)
    assert (output/'current.json').read_bytes()==pointer


def test_concurrent_identical_publications_reuse_verified_version(tmp_path):
    root=write_sources(tmp_path/'source',{'main.py':'def main(): pass\n'})
    bundle,ir,markdown,report=analyze(root)
    def run():
        return publish(tmp_path/'out',bundle,ir,markdown,report,render_map(bundle))
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions=list(pool.map(lambda _:run(),range(2)))
    assert versions[0]==versions[1]
    assert json.loads((versions[0]/'manifest.json').read_bytes())['acceptance']=='draft'


def test_repeated_zip_cli_import_reuses_identical_publication(tmp_path):
    archive=tmp_path/'source.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('project/entry.py','def helper(): pass\ndef entry(): helper()\n')
    output=tmp_path/'out'
    for _ in range(2):
        assert main(['analyze','--zip',str(archive),'--output',str(output)])==0
    assert len(list((output/'versions').iterdir()))==1
