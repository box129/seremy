"""Select immutable documentation evidence for a repository path or map item."""
import copy
import re

from seremy.document_drafts import evidence_context
from seremy.documentation import document_digest
from seremy.contracts import canonical_bytes, sha256_hex


def scoped_context(loader, document, scope, question, offset, limit, read_citation, *, purpose="overview"):
    if not isinstance(purpose, str) or purpose not in {"overview", "walkthrough"}:
        raise ValueError("Choose an overview or a walkthrough")
    if not isinstance(scope, dict) or set(scope) != {"kind", "value"}:
        raise ValueError("Documentation scope requires kind and value")
    kind, value = scope["kind"], scope["value"]
    if not isinstance(value, str) or not value or not isinstance(question, str) or len(question) > 2000:
        raise ValueError("Choose a scope and a question of at most 2000 characters")
    sources = loader.contents["source_texts"]
    entity_ids = set()
    candidate_ids = set()
    if kind == "file":
        files = {value} if value in sources else set()
    elif kind == "folder":
        files = {file for file in sources if value == "." or file.startswith(value + "/")}
    elif kind == "entity":
        if not value.startswith("ent:"):
            raise ValueError("Choose an observed declaration")
        entity = loader.lookup_entity(value)
        files = {entity["file_id"]} if entity else set()
        entity_ids.add(value)
    elif kind == "connection":
        site = loader.occurrence(value)
        if site:
            occurrence = site["occurrence"]
            files = {occurrence["file_id"]}
            candidate_ids.add(value)
        else:
            module = next((edge for edge in loader.contents.get("module_dependencies", {}).get("artifact", {}).get("edges", [])
                           if "module:" + edge["candidate_id"] == value), None)
            if module is None:
                raise ValueError("Choose an observed connection")
            files = {module["source_file"], module["target_file"]}
            candidate_ids.add(value)
    else:
        raise ValueError("Unknown documentation scope kind")
    if not files:
        raise ValueError("Documentation scope is outside this snapshot")

    def relevant(claim):
        subject = claim.get("subject", {})
        if kind == "entity":
            return any(subject.get(key) in entity_ids for key in ("entity_id", "source", "target"))
        if kind == "connection":
            return any(c.get("candidate_id") in candidate_ids for c in claim.get("citations", []))
        return subject.get("file_id") in files or any(c["file_id"] in files for c in claim.get("citations", []))

    # Retrieve direct static neighbors without claiming runtime reachability.
    neighbors = set()
    for edge in loader.contents.get("module_dependencies", {}).get("artifact", {}).get("edges", []):
        if edge["source_file"] in files:
            neighbors.add(edge["target_file"])
        if edge["target_file"] in files:
            neighbors.add(edge["source_file"])
    neighbors &= set(sources) - files
    terms = set(re.findall(r"[a-zA-Z_][a-zA-Z_0-9]{2,}", question.lower()))
    terms -= {"the", "does", "what", "how", "this", "that", "with", "from", "and", "for"}
    importance = {}
    modules = loader.contents.get("module_dependencies", {}).get("artifact", {}).get("edges", [])
    entry_files = {file for file in files if file.rsplit("/", 1)[-1].split(".")[0]
                   in {"index", "main", "app", "__init__"}}
    entry_targets = {}
    for edge in sorted(modules, key=lambda edge: (edge["source_file"], edge["span"][0])):
        target = edge["target_file"]
        importance[target] = importance.get(target, 0) + 1
        if edge["source_file"] in entry_files:
            entry_targets.setdefault(target, len(entry_targets))
    def rank(file):
        words = set(re.findall(r"[a-zA-Z_][a-zA-Z_0-9]{2,}", file.lower()))
        entry = file.rsplit("/", 1)[-1].split(".")[0] in {"index", "main", "app", "__init__"}
        return (-len(terms & words), -int(entry), entry_targets.get(file, len(entry_targets)),
                -importance.get(file, 0), file)

    ordered_files = sorted(files, key=rank) + sorted(neighbors, key=rank)
    related = set(ordered_files)
    def claim_files(claim):
        subject = claim.get("subject", {})
        result = {c["file_id"] for c in claim.get("citations", [])}
        result.add(subject.get("file_id"))
        return result

    claims = [claim for claim in document["claims"] if relevant(claim) or claim_files(claim) & neighbors]
    if kind in {"file", "folder"}:
        # Every captured file can be documented, including files without symbols.
        previews = [{"claim_id": "scope-file-" + str(index), "kind": "guide",
                     "text": f"`{file}` is captured source evidence for the selected scope or its static neighbors.",
                     "subject": {"file_id": file}, "citations": [], "witnesses": [{"stage": "snapshot"}]}
                    for index, file in enumerate(ordered_files)]
        # Interleave one evidence-bearing claim per file before filling the page.
        # A large folder must not consume the entire page with alphabetic previews.
        first = []
        remaining = list(claims)
        for preview in previews:
            file = preview["subject"]["file_id"]
            match = next((c for c in remaining if file in claim_files(c)), None)
            first.append(match or preview)
            if match is not None:
                remaining.remove(match)
        claims = first + remaining
    else:
        claims += [{"claim_id": "related-file-" + str(index), "kind": "guide",
                    "text": f"`{file}` is a captured static dependency or consumer of the selected scope.",
                    "subject": {"file_id": file}, "citations": [], "witnesses": [{"stage": "snapshot"}]}
                   for index, file in enumerate(sorted(neighbors, key=rank))]
    selected = copy.copy(document)
    selected["claims"] = claims
    dependencies = document["dependencies"]
    selected["sections"] = [{"section_id": "selected-scope", "title": f"{kind.title()} - {value}",
                             "claim_ids": [c["claim_id"] for c in claims], "dependencies": dependencies}]
    result = evidence_context(selected, "selected-scope", offset, limit, read_citation, loader)
    result["document_digest"] = document_digest(document)
    result["requested_scope"] = scope
    result["question"] = question
    result["scope_file_count"] = len(files)
    result["documentation_purpose"] = purpose
    result["related_file_count"] = len(neighbors)
    result["retrieval_policy"] = "Selected scope and direct captured static imports/consumers. File ordering uses question terms and entry filenames."
    result["available_files"] = ordered_files[:100]
    result["omitted_file_inventory_count"] = max(0, len(related) - 100)
    result["title"] = ("Start here" if purpose == "overview" else "How it works") + " - " + value
    result.pop("context_digest")
    result["context_digest"] = sha256_hex(canonical_bytes(result))
    return result
