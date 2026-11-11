"""Run with python -m seremy analyze ROOT --output OUTPUT."""
import argparse
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import json
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
import zipfile
import hashlib

from seremy.product import analyze, publish
from seremy.viewer import render_map
from seremy.bundle import BundleLoader
from seremy.architecture import shortest_path
from seremy.git_input import run_git


def extract_zip(archive, destination):
    destination=Path(destination).resolve()
    used=set();total=0
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist()
        if len(entries)>5000:
            raise ValueError("archive has more than 5000 entries")
        for item in entries:
            path=PurePosixPath(item.filename.replace("\\","/"))
            if path.is_absolute() or any(p in ("..","") or ":" in p for p in path.parts):
                raise ValueError("unsafe archive path")
            if any(part.endswith((".", " ")) for part in path.parts):
                raise ValueError("unsafe archive path")
            if any(part.casefold()==".git" for part in path.parts):
                continue
            reserved={"con","prn","aux","nul",*("com"+str(i) for i in range(1,10)),
                      *("lpt"+str(i) for i in range(1,10))}
            if any(part.split(".")[0].casefold() in reserved for part in path.parts):
                raise ValueError("unsafe archive device path")
            if stat.S_ISLNK(item.external_attr>>16):
                raise ValueError("archive links are unsupported")
            target=destination.joinpath(*path.parts)
            key=str(target).casefold()
            if key in used:
                raise ValueError("duplicate archive path")
            used.add(key)
            total+=item.file_size
            if total>64*1024*1024 or item.file_size>1024*1024:
                raise ValueError("archive exceeds extraction limits")
            if item.is_dir():
                target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as source, target.open("xb") as out:
                    count=0
                    while block:=source.read(64*1024):
                        count+=len(block)
                        if count>item.file_size:
                            raise ValueError("archive size mismatch")
                        out.write(block)


@contextmanager
def input_root(args):
    args.snapshot_identity=None
    args.use_git=True
    if args.zip or args.git_url:
        with tempfile.TemporaryDirectory(prefix="seremy-repo-") as directory:
            root=Path(directory)
            if args.zip:
                with Path(args.zip).open("rb") as archive:
                    archive_digest=hashlib.file_digest(archive,"sha256").hexdigest()
                args.snapshot_identity={"repository_id":"zip:sha256:"+archive_digest,
                                        "declared_root":"archive:/"+archive_digest}
                args.use_git=False
                extract_zip(args.zip,root)
                entries=list(root.iterdir())
                if len(entries)==1 and entries[0].is_dir():
                    root=entries[0]
            else:
                url=urlsplit(args.git_url)
                if url.scheme!="https" or not url.hostname or url.username or url.password:
                    raise ValueError("Git source must be an HTTPS URL without embedded credentials")
                command=["clone","--depth=1","--no-recurse-submodules"]
                if args.revision:
                    command+=["--branch",args.revision]
                command+=["--",args.git_url,str(root/"checkout")]
                run_git(command,check=True,timeout=120,capture_output=True)
                root=root/"checkout"
                revision=run_git(["-C",str(root),"rev-parse","HEAD"],check=True,
                                 capture_output=True,timeout=10).stdout.decode().strip()
                args.snapshot_identity={"repository_id":"git:"+args.git_url,
                                        "declared_root":"git:"+args.git_url+"@"+revision}
            yield root
    else:
        if not args.root:
            raise ValueError("choose a local folder, --zip or --git-url")
        yield Path(args.root).resolve()


def main(argv=None):
    parser=argparse.ArgumentParser(prog="seremy")
    commands=parser.add_subparsers(dest="command",required=True)
    scan=commands.add_parser("analyze")
    scan.add_argument("root",nargs="?")
    inputs=scan.add_mutually_exclusive_group()
    inputs.add_argument("--zip")
    inputs.add_argument("--git-url")
    scan.add_argument("--revision")
    scan.add_argument("--output",required=True)
    scan.add_argument("--policy",help="JSON forbidden-boundary rules and reject_cycles flag")
    path=commands.add_parser("path")
    path.add_argument("--graph",required=True)
    path.add_argument("--from-id",required=True)
    path.add_argument("--to-id",required=True)
    path.add_argument("--max-visited",type=int,default=10000)
    args=parser.parse_args(argv)
    try:
        if args.command=="path":
            loader=BundleLoader.from_file(Path(args.graph))
            print(json.dumps(shortest_path(loader.edges(),args.from_id,args.to_id,max_visited=args.max_visited),indent=2))
            return 0
        if args.root and (args.zip or args.git_url):
            raise ValueError("choose exactly one repository input")
        if args.revision and not args.git_url:
            raise ValueError("--revision requires --git-url")
        policy=json.loads(Path(args.policy).read_text(encoding="utf8")) if args.policy else None
        with input_root(args) as root:
            output=Path(args.output).resolve()
            if output==root or root.is_relative_to(output):
                raise ValueError("output must not contain the input repository")
            if output.is_relative_to(root) and output!=root/".seremy-artifacts":
                raise ValueError("use .seremy-artifacts or an output directory outside the input")
            bundle,ir,markdown,checks=analyze(root,policy=policy,
                snapshot_identity=args.snapshot_identity,use_git=args.use_git,
                progress=lambda msg:print(msg,file=sys.stderr,flush=True))
            target=publish(output,bundle,ir,markdown,checks,render_map(bundle))
        print(json.dumps({"publication":str(target),"acceptance":"draft","map":str(target/"map.html"),
                          "documentation":str(target/"architecture.md")},indent=2))
        return 0
    except KeyboardInterrupt:
        print("Analysis cancelled; the current publication pointer was retained.",file=sys.stderr)
        return 130
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,zipfile.BadZipFile) as error:
        print(str(error),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

