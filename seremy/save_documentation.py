"""Save an existing, verified local MCP draft to a user-selected destination."""
import os
from pathlib import Path
import tempfile


def save_documentation(bridge, request):
    destination = request.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("Enter the complete destination path, including the .md filename")
    path = Path(destination.strip())
    if not path.is_absolute() or path.suffix.lower() != ".md":
        raise ValueError("Choose an absolute path ending in .md")
    if not path.parent.is_dir():
        raise ValueError("The destination folder does not exist")
    receipt = bridge.tool({"tool": "documentation_draft", **{
        key: request.get(key) for key in ("view_id", "digest", "request_id")}})
    raw = receipt["draft"]["markdown"].encode("utf8")
    # Publish a completely written file atomically. Linking refuses any existing
    # destination, including a symlink, while retries may acknowledge identical data.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".seremy-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.stat().st_size != len(raw) or path.read_bytes() != raw:
                raise ValueError("A different file already exists there. Choose another filename.") from None
        return {"status": "saved", "path": str(path), "bytes": len(raw), "draft_id": receipt["draft"]["draft_id"]}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
