"""Independent truth and boundary cases for the frozen JS/JSX/TSX profile."""
import copy
import json
from pathlib import Path

import pytest

from seremy.bundle import BundleLoader
from seremy.contracts import PROFILE_ID, sha256_hex
from seremy.language_profiles import ECMASCRIPT_PROFILE, ECMASCRIPT_PRODUCT_PROFILE, ECMASCRIPT_BINDING_PROFILE
from seremy.product import analyze, publish
from seremy.snapshot import collect_snapshot
from seremy.staleness import check_staleness, citation_is_current
from seremy.tests.test_resolver import _pipeline
from seremy.viewer import render_map

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/ecmascript-slice'


def make_sources(root,sources):
    for name,text in sources.items():
        file=root/name;file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(text if isinstance(text,bytes) else text.encode('utf8'))


def line(source,span):
    return source[:span[0]].count(b'\n')+1


@pytest.fixture(scope='module')
def observed():
    return analyze(FIXTURE)


def test_exact_independent_relationship_truth_and_no_jsx_runtime_edges(observed):
    bundle,ir,markdown,validation=observed;c=bundle['contents'];truth=json.loads((FIXTURE/'truth.json').read_text())
    entities={e['entity_id']:e for e in c['s03']['artifact']['entities']};actual=[]
    for edge in c['s03']['artifact']['edges']:
        source,target=entities[edge['source']],entities[edge['target']]
        for site in edge['occurrences']:
            raw=(FIXTURE/site['file_id']).read_bytes()
            actual.append(dict(source_file=source['file_id'],source_name=source['name'],target_file=target['file_id'],target_name=target['name'],token=raw[slice(*site['span'])].decode(),line=line(raw,site['span'])))
            assert site['evidence']['method']==ECMASCRIPT_BINDING_PROFILE
    assert sorted(actual,key=str)==sorted(truth['relationships'],key=str)
    assert not any(entities[e['target']]['name']=='Child' for e in c['s03']['artifact']['edges'])
    assert validation['pre_generation']['status']==validation['post_generation']['status']=='pass'
    assert ir['profile']==ECMASCRIPT_PROFILE and '5 source files' in ir['label']['slice_scope']
    assert 'original' in markdown


def test_jsx_tags_and_limitations_match_independent_truth(observed):
    c=observed[0]['contents'];truth=json.loads((FIXTURE/'truth.json').read_text());actual=[];limits=[]
    for record in c['s03']['artifact']['resolutions']:
        raw=(FIXTURE/record['file_id']).read_bytes();number=line(raw,record['candidate_span'])
        if record['candidate_kind']=='jsx_tag':
            assert record['outcome']=='NOT_PROCESSED' and not record['attempted']
            assert record['reason']=='jsx_runtime_semantics_outside_profile'
            actual.append(dict(file=record['file_id'],name=record['name'],line=number))
        if record['file_id']=='limitations.js' and record['attempted']:
            limits.append(dict(name=record['name'],line=number,outcome=record['outcome'],reason=record['reason']))
    assert sorted(actual,key=str)==sorted(truth['jsx_tags'],key=str)
    assert limits==truth['limitations']
    assert c['coverage']['s02']==dict(source_file_count=5,parsed_file_records=5,complete=5,partial=0,failed=0,not_processed=0)
    assert c['coverage']['s03']['candidate_count']==22 and c['coverage']['s03']['attempted_count']==9


def test_versioned_profiles_script_kinds_and_compiler_provenance(observed):
    c=observed[0]['contents'];assert c['profile']==ECMASCRIPT_PRODUCT_PROFILE
    assert c['s02']['artifact']['profile']==c['s03']['artifact']['profile']==ECMASCRIPT_PROFILE
    assert c['s03']['artifact']['binding_profile']==ECMASCRIPT_BINDING_PROFILE
    for parsed in c['s02']['artifact']['files']:
        coverage=parsed['construct_coverage'];assert coverage['typescript_version']=='5.9.3'
        assert coverage['semantic_diagnostics']=='not_run'
        assert coverage['script_kind']==('TSX' if parsed['file_id'].endswith('.tsx') else 'JSX' if parsed['file_id'].endswith('.jsx') else 'JS')
        for candidate in parsed['candidates']:
            if 'binding' in candidate:
                context=candidate['binding']['context'];options=context['compiler_options']
                assert context['method']==ECMASCRIPT_BINDING_PROFILE
                assert options['allowJs'] is True and options['checkJs'] is False and options['noEmit'] is True and options['jsx']==1
                assert dict(context['script_kinds'])['App.tsx']=='TSX'
    raw=(FIXTURE/'helper.js').read_bytes();entity=next(e for e in c['s03']['artifact']['entities'] if e['name']=='original')
    assert entity['name_span'][0]==raw.index(b'original')


@pytest.mark.parametrize('extension',['js','jsx','tsx'])
def test_bom_unicode_crlf_cross_checked_bytes_and_jsx_syntax(tmp_path,extension):
    text='\ufeff// é 🦊\r\nexport function chosen(){return 1;}\r\nexport function App(){return <div>{chosen()}</div>;}\r\n'
    make_sources(tmp_path,{'view.'+extension:text});bundle,*_=analyze(tmp_path,use_git=False);c=bundle['contents']
    assert c['coverage']['s02']['complete']==1
    edge=c['s03']['artifact']['edges'][0];site=edge['occurrences'][0];raw=text.encode()
    assert site['span']==[raw.rindex(b'chosen'),raw.rindex(b'chosen')+6]
    target=next(e for e in c['s03']['artifact']['entities'] if e['name']=='chosen')
    assert target['name_span']==[raw.index(b'chosen'),raw.index(b'chosen')+6]
    assert c['coverage']['s03']['outcome_counts']['NOT_PROCESSED']==1


@pytest.mark.parametrize('name,text',[('broken.jsx','export function broken(){return <div>;'),('typed.js','export function broken(value: number){return value;}'),('view.ts','export function broken(){return <div/>;}')])
def test_syntax_and_js_grammar_failures_are_partial_not_complete(tmp_path,name,text):
    make_sources(tmp_path,{name:text,'enable.js':'export function enable(){}'});bundle,*_=analyze(tmp_path,use_git=False)
    record=next(r for r in bundle['contents']['s02']['artifact']['files'] if r['file_id']==name)
    assert record['bucket']=='partial' and record['diagnostics']
    assert not bundle['contents']['s03']['artifact']['edges']


def test_invalid_utf8_remains_failed_and_not_displayable(tmp_path):
    make_sources(tmp_path,{'bad.jsx':b'\xff\xfe'});bundle,*_=analyze(tmp_path,use_git=False);c=bundle['contents']
    assert c['profile']==ECMASCRIPT_PRODUCT_PROFILE and c['coverage']['s02']['failed']==1
    assert c['s02']['artifact']['files'][0]['reason']=='not_utf8' and c['source_texts']=={}
    assert c['s03']['artifact']['edges']==[]


def test_config_aliases_use_snapshot_with_enforced_no_emit_options(tmp_path):
    config={'compilerOptions':{'baseUrl':'.','paths':{'@target':['lib/helper.js']},'allowJs':False,'checkJs':True,'jsx':'react-jsx','noEmit':False}}
    make_sources(tmp_path,{'tsconfig.json':json.dumps(config),'lib/helper.js':'export function helper(){return 1;}',
        'src/main.jsx':"import {helper as chosen} from '@target'; export function App(){return <div>{chosen()}</div>;}"})
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()};bundle,*_=analyze(tmp_path,use_git=False);c=bundle['contents']
    assert len(c['s03']['artifact']['edges'])==1
    context=next(candidate['binding']['context'] for row in c['s02']['artifact']['files'] for candidate in row['candidates'] if 'binding' in candidate)
    assert context['config_sha256']==sha256_hex((tmp_path/'tsconfig.json').read_bytes())
    assert context['compiler_options']['allowJs'] and context['compiler_options']['noEmit']
    assert context['compiler_options']['jsx']==1 and context['compiler_options']['checkJs'] is False
    assert before=={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_unselected_javascript_file_on_disk_cannot_supply_a_target(tmp_path):
    make_sources(tmp_path,{'main.jsx':"import {helper} from './hidden.js'; export function App(){return <div>{helper()}</div>;}",'hidden.js':'export function helper(){}'})
    from seremy.resolver import Resolver
    from seremy.parsing import artifact_digest
    parsed=_pipeline(tmp_path,['main.jsx']);result=Resolver(parsed,expected_s02_digest=artifact_digest(parsed)).resolve()
    assert not result.edges
    assert any(r.outcome=='MISSING' and r.reason=='unresolved_import' for r in result.resolutions)


@pytest.mark.parametrize('assignment',['chosen = replacement;','[chosen] = [replacement];','({ chosen } = { chosen: replacement });'])
def test_reassignment_blocks_static_target_claims(tmp_path,assignment):
    make_sources(tmp_path,{'main.js':'function chosen(){return 1;} const replacement=()=>2; '+assignment+' export function entry(){return chosen();}'})
    bundle,*_=analyze(tmp_path,use_git=False);records=bundle['contents']['s03']['artifact']['resolutions']
    call=next(r for r in records if r['name']=='chosen' and r['attempted'])
    assert call['outcome']=='UNSUPPORTED' and call['reason']=='binding_reassigned_in_snapshot'
    assert not bundle['contents']['s03']['artifact']['edges']


@pytest.mark.parametrize('statement',['chosen.label="label";','function change(chosen){chosen=0;}'])
def test_properties_and_shadowed_parameters_do_not_reassign_the_function(tmp_path,statement):
    make_sources(tmp_path,{'main.js':'function chosen(){return 1;} '+statement+' export function entry(){return chosen();}'})
    bundle,*_=analyze(tmp_path,use_git=False);assert len(bundle['contents']['s03']['artifact']['edges'])==1


def test_arrow_callback_is_not_invented_as_an_app_to_helper_relationship(tmp_path):
    make_sources(tmp_path,{'main.jsx':'function helper(){} export function App(){return <div onClick={()=>helper()}/>;}'})
    bundle,*_=analyze(tmp_path,use_git=False);c=bundle['contents'];assert not c['s03']['artifact']['edges']
    assert any(r['reason']=='source_owner_not_established' for r in c['s03']['artifact']['resolutions'])


def test_legacy_universe_and_binding_options_stay_unchanged(tmp_path):
    make_sources(tmp_path,{'main.ts':'function chosen(){return 1;} export function entry(){return chosen();}','node_modules/ignored.js':'export function hidden(){}'})
    manifest,_,_=collect_snapshot(tmp_path,use_git=False);assert manifest.profile_id==PROFILE_ID
    assert manifest.policy.included_extensions==frozenset({'.ts','.py','.json','.toml'})
    bundle,*_=analyze(tmp_path,use_git=False);c=bundle['contents'];assert c['profile']=='seremy-local-product-v0.1'
    assert c['s02']['artifact']['profile']==PROFILE_ID and c['s03']['artifact']['binding_profile']=='typescript-checker-v0.2'
    context=next(candidate['binding']['context'] for row in c['s02']['artifact']['files'] for candidate in row['candidates'] if 'binding' in candidate)
    assert context['method']=='typescript-checker-v0.2' and 'allowJs' not in context['compiler_options'] and 'script_kinds' not in context


def test_new_profile_keeps_python_separate_and_conserves_all_sources(tmp_path):
    make_sources(tmp_path,{'main.js':'function chosen(){} export function entry(){chosen();}','main.py':'def chosen(): pass\ndef entry(): chosen()\n'})
    bundle,*_=analyze(tmp_path,use_git=False);c=bundle['contents'];assert c['coverage']['s02']['source_file_count']==2
    assert c['s03']['artifact']['binding_profile']=='mixed-ecmascript-static-v0.1' and len(c['s03']['artifact']['edges'])==2


def test_config_staleness_even_without_a_call_observation(tmp_path):
    make_sources(tmp_path,{'view.jsx':'export function App(){return <div/>;}'})
    bundle,*_=analyze(tmp_path,use_git=False);loader=BundleLoader(bundle);assert not check_staleness(loader,tmp_path)['stale']
    (tmp_path/'tsconfig.json').write_text('{}');assert check_staleness(loader,tmp_path)['config_changed']
    assert not citation_is_current(loader,tmp_path,'view.jsx',(0,6))


def test_multi_project_config_is_explicitly_outside_profile(tmp_path):
    make_sources(tmp_path,{'view.jsx':'export function App(){return <div/>;}','tsconfig.json':'{"extends":"./other.json"}'})
    with pytest.raises(RuntimeError,match='multi-project snapshot profile'):analyze(tmp_path,use_git=False)


def test_publication_manifest_and_map_expose_actual_new_profile(tmp_path,observed):
    bundle,ir,markdown,report=observed;html=render_map(bundle);published=publish(tmp_path,bundle,ir,markdown,report,html)
    assert json.loads((published/'manifest.json').read_text())['profile']==ECMASCRIPT_PRODUCT_PROFILE
    assert ECMASCRIPT_PRODUCT_PROFILE in html and 'jsx_runtime_semantics_outside_profile' in html
    BundleLoader(copy.deepcopy(bundle))


@pytest.mark.parametrize('readable',[False,True])
def test_skipped_extended_source_preserves_the_declared_profile(tmp_path,readable):
    sources={'oversized.tsx':b'x'*(1024*1024+1)}
    if readable:sources['main.ts']='function helper(){} export function outer(){return ()=>helper();}'
    make_sources(tmp_path,sources);bundle,*_=analyze(tmp_path,use_git=False);c=bundle['contents']
    assert c['profile']==ECMASCRIPT_PRODUCT_PROFILE
    assert c['s02']['artifact']['profile']==c['s03']['artifact']['profile']==ECMASCRIPT_PROFILE
    assert c['coverage']['s02']['source_file_count']==1+readable and c['coverage']['s02']['not_processed']==1
    assert not c['s03']['artifact']['edges']
    if readable:
        assert c['s03']['artifact']['binding_profile']==ECMASCRIPT_BINDING_PROFILE
        assert c['s03']['artifact']['resolutions'][0]['reason']=='source_owner_not_established'
