import subprocess
from seremy.snapshot import collect_snapshot


def test_git_scope_keeps_tracked_ignored_and_excludes_untracked_ignored(tmp_path):
    subprocess.run(["git","init",str(tmp_path)],check=True,capture_output=True)
    (tmp_path/".gitignore").write_text("ignored.py\ntracked.py\n")
    (tmp_path/"ignored.py").write_text("print('ignored')")
    (tmp_path/"tracked.py").write_text("def tracked(): pass")
    (tmp_path/"normal.py").write_text("def normal(): pass")
    subprocess.run(["git","-C",str(tmp_path),"add","--force","tracked.py"],check=True,capture_output=True)
    manifest,contents,scope=collect_snapshot(tmp_path)
    assert scope["mode"]=="git_tracked_and_nonignored"
    assert set(contents)=={"tracked.py","normal.py"}
    assert manifest.eligible_count==2


def test_plain_walk_records_pruned_subtree(tmp_path):
    (tmp_path/"node_modules").mkdir()
    (tmp_path/"node_modules"/"vendor.ts").write_text("export function hidden(){}")
    (tmp_path/"source.py").write_text("def source(): pass")
    manifest,contents,scope=collect_snapshot(tmp_path)
    assert set(contents)=={"source.py"}
    assert any(d["reason"]=="pruned_subtree" for d in scope["diagnostics"])
    manifest.reconcile()

