"""Analysis milestones shared by local and hosted launchers."""
import json
import os
from pathlib import Path


MILESTONES = {
    "Preparing repository": (2, "Preparing repository"),
    "Resolving revision": (4, "Resolving repository revision"),
    "Downloading repository": (7, "Downloading repository"),
    "S01 · snapshot": (12, "Discovering and capturing files"),
    "S02 · parsing": (24, "Parsing source files"),
    "S03 · binding": (46, "Resolving dependencies"),
    "S04 · framework evidence": (62, "Analyzing frameworks"),
    "S05 · structural components": (70, "Identifying components"),
    "S06 · relationship views": (78, "Building relationships"),
    "S07 · graph validation": (86, "Validating architecture"),
    "S08 · documentation": (91, "Preparing architecture guide"),
    "S07 · generated output validation": (95, "Checking generated output"),
    "Publishing draft": (98, "Publishing map and guide"),
}


def milestone(message):
    percent, label = MILESTONES[message]
    return {"progress": percent, "stage": label}


def report_progress(message):
    destination = os.environ.get("SEREMY_PROGRESS_FILE")
    if destination:
        path = Path(destination)
        temporary = path.with_suffix(".pending")
        temporary.write_text(json.dumps(milestone(message)), encoding="utf8")
        os.replace(temporary, path)
