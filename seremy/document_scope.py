"""Select immutable documentation evidence for a repository path or map item."""
import copy

from seremy.document_drafts import evidence_context
from seremy.documentation import document_digest


def scoped_context(loader, document, scope, question, offset, limit, read_citation):
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

    claims = [claim for claim in document["claims"] if relevant(claim)]
    if kind in {"file", "folder"}:
        # Every captured file can be documented, including files without symbols.
        previews = [{"claim_id": "scope-file-" + str(index), "kind": "guide",
                     "text": f"`{file}` is a captured source file in the selected documentation scope.",
                     "subject": {"file_id": file}, "citations": [], "witnesses": [{"stage": "snapshot"}]}
                    for index, file in enumerate(sorted(files))]
        claims = previews + claims
    selected = copy.copy(document)
    selected["claims"] = claims
    dependencies = document["dependencies"]
    selected["sections"] = [{"section_id": "selected-scope", "title": f"{kind.title()} · {value}",
                             "claim_ids": [c["claim_id"] for c in claims], "dependencies": dependencies}]
    result = evidence_context(selected, "selected-scope", offset, limit, read_citation, loader)
    result["document_digest"] = document_digest(document)
    result["requested_scope"] = scope
    result["question"] = question
    result["scope_file_count"] = len(files)
    return result
