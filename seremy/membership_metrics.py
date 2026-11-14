"""Frozen Stage 5 pair/coverage/matching rules for bounded file partitions."""
from fractions import Fraction
from functools import lru_cache
from itertools import combinations


def rate(numerator, denominator, reason="zero_denominator"):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None,
            "status": "computed" if denominator else "not_applicable",
            "reason": None if denominator else reason}


def unavailable(reason):
    return {"numerator": None, "denominator": None, "value": None, "status": "not_applicable", "reason": reason}


def same_group(mapping, left, right):
    # Missing/unassigned IDs are distinct singleton placeholders in pair space.
    return mapping.get(left) is not None and mapping.get(left) == mapping.get(right)


def pair_metrics(universe, reference, predicted):
    universe = sorted(set(universe))
    positive, predicted_positive, tp, fp, fn = 0, 0, 0, 0, 0
    for left, right in combinations(universe, 2):
        gold = same_group(reference, left, right)
        emitted = same_group(predicted, left, right)
        positive += gold
        predicted_positive += emitted
        tp += gold and emitted
        fp += emitted and not gold
        fn += gold and not emitted
    pairs = len(universe) * (len(universe) - 1) // 2
    negative = pairs - positive
    metrics = {"precision": rate(tp, predicted_positive), "recall": rate(tp, positive, "no_reference_positive_pairs"),
               "f1": rate(2 * tp, 2 * tp + fp + fn) if positive else unavailable("no_reference_positive_pairs"),
               "false_merge": rate(fp, negative, "no_reference_negative_pairs"),
               "false_split": rate(fn, positive, "no_reference_positive_pairs")}
    metrics["balanced_correctness"] = (rate((1 - fp / negative) + (1 - fn / positive), 2)
                                        if negative and positive else unavailable("reference_requires_positive_and_negative_pairs"))
    return {"counts": {"universe": len(universe), "pairs": pairs, "reference_positive": positive,
                       "reference_negative": negative, "predicted_positive": predicted_positive, "tp": tp, "fp": fp, "fn": fn},
            "metrics": metrics}


def partition_groups(universe, mapping):
    groups = {}
    for entity in universe:
        owner = mapping.get(entity)
        if owner is not None:
            groups.setdefault(owner, set()).add(entity)
    return groups


def membership_matching(universe, reference, predicted):
    """Exact positive-Jaccard maximum matching with frozen lexicographic ties.

    This controlled profile supports at most twelve nonempty groups per side.
    That bound keeps the exact subset dynamic program small and explicit.
    """
    gold = partition_groups(universe, reference)
    emitted = partition_groups(universe, predicted)
    refs, preds = sorted(gold), sorted(emitted)
    if max(len(refs), len(preds)) > 12:
        raise ValueError("Bounded matching profile supports at most twelve groups per side")
    weights = {(r, p): Fraction(len(gold[r] & emitted[p]), len(gold[r] | emitted[p])) for r in refs for p in preds}

    @lru_cache(None)
    def solve(index, used):
        if index == len(refs):
            return Fraction(0), ()
        best = solve(index + 1, used)
        for position, predicted_id in enumerate(preds):
            weight = weights[refs[index], predicted_id]
            if used & (1 << position) or not weight:
                continue
            score, pairs = solve(index + 1, used | (1 << position))
            choice = score + weight, ((refs[index], predicted_id), *pairs)
            if choice[0] > best[0] or (choice[0] == best[0] and choice[1] < best[1]):
                best = choice
        return best

    _, matched = solve(0, 0)
    return [{"reference": r, "predicted": p, "jaccard": str(weights[r, p])} for r, p in matched]


def normalize_name(name):
    return " ".join(name.casefold().split())


def score_partition(universe, reference, output, *, ambiguous=(), aliases=None):
    universe = sorted(set(universe))
    scope = set(universe)
    if set(reference) != scope or not set(ambiguous) <= scope:
        raise ValueError("Reference partition and ambiguous IDs must bind the complete authored universe")
    if output["status"] not in ("completed", "failed", "unsupported"):
        raise ValueError("Evaluation output requires a terminal execution status")
    owners = output.get("owners", {}) if output["status"] == "completed" else {}
    if not isinstance(owners, dict) or not all(isinstance(k, str) and isinstance(v, list) and all(isinstance(g, str) and g for g in v) for k, v in owners.items()):
        raise ValueError("File ownership must retain lists of proposed group IDs")
    recognized = (set(output.get("recognized", [])) | set(owners)) if output["status"] != "failed" else set()
    conflicts = {key for key, value in owners.items() if key in scope and len(set(value)) > 1}
    assigned = {key: next(iter(set(value))) for key, value in owners.items() if key in scope and len(set(value)) == 1}
    missing = scope - recognized
    unassigned = {key for key in scope if not owners.get(key)}
    extras = (set(owners) | recognized) - scope
    extra_groups = {group for key, groups in owners.items() if key in extras for group in groups}
    in_scope_groups = {group for key, groups in owners.items() if key in scope for group in groups}
    coverage = {"recognition": rate(len(recognized & scope), len(scope), "empty_scope"),
                "assignment": rate(len(assigned), len(scope), "empty_scope"),
                "unassigned": rate(len(unassigned), len(scope), "empty_scope"),
                "conflict": rate(len(conflicts), len(scope), "empty_scope"),
                "extra": rate(len(extras), 1)}
    reason = None
    if output["status"] == "failed":
        reason = "failed_run"
        coverage["extra"] = unavailable("unparseable_output")
    elif output["status"] == "unsupported":
        reason = "unsupported_target"
        for key in ("assignment", "unassigned", "conflict"):
            coverage[key] = unavailable(reason)
    elif conflicts:
        reason = "conflicting_ownership"
    primary = sorted(scope - set(ambiguous))
    pairs = {"counts": None, "metrics": {key: unavailable(reason) for key in ("precision", "recall", "f1", "false_merge", "false_split", "balanced_correctness")}}
    matching, alias_accuracy = [], unavailable(reason or "no_reference_groups")
    if reason is None:
        pairs = pair_metrics(primary, reference, assigned)
        matching = membership_matching(primary, reference, assigned)
        groups = partition_groups(primary, reference)
        matches = {m["reference"]: m["predicted"] for m in matching}
        names = output.get("names", {})
        alias_accuracy = rate(sum(group in matches and normalize_name(names.get(matches[group], "")) in
                                  {normalize_name(alias) for alias in (aliases or {}).get(group, [])} for group in groups), len(groups))
    return {"status": output["status"], "valid_partition": reason is None, "reason": reason,
            "coverage": coverage, "pairs": pairs, "matching": matching, "alias_accuracy": alias_accuracy,
            "name_rubric": unavailable("two_independent_reviewers_required"),
            "description_rubric": unavailable("two_independent_reviewers_required"),
            "diagnostics": {"missing_ids": sorted(missing), "unassigned_ids": sorted(unassigned),
                            "missing_membership_ids": sorted(scope - set(owners)),
                            "conflicting_ids": sorted(conflicts), "extra_ids": sorted(extras),
                            "spurious_extra_only_groups": sorted(extra_groups - in_scope_groups)}}


def alternative_sensitivity(universe, references, output, *, ambiguous):
    if not references or any(set(r) != set(universe) for r in references):
        raise ValueError("Sensitivity requires complete alternative partitions")
    scores = [score_partition(universe, ref, output) for ref in references]
    owners = output.get("owners", {})
    accepted = False
    # Ownership labels can differ. Compare the complete co-membership pattern,
    # including all unambiguous anchors, without a per-file alternative choice.
    assigned = {key: value[0] for key, value in owners.items() if len(value) == 1}
    if output["status"] == "completed" and not any(len(set(owners.get(k, []))) > 1 for k in universe):
        accepted = any(all(same_group(assigned, a, b) == same_group(ref, a, b) for a, b in combinations(universe, 2)
                           if a in ambiguous or b in ambiguous) and
                       all(bool(owners.get(k)) == (ref[k] is not None) for k in ambiguous) for ref in references)
    values = [s["pairs"]["metrics"]["f1"]["value"] for s in scores if s["pairs"]["metrics"]["f1"]["value"] is not None]
    return {"whole_alternative_scores": scores, "f1_range": {"minimum": min(values) if values else None, "maximum": max(values) if values else None},
            "ambiguity_acceptance": rate(len(ambiguous) if accepted else 0, len(ambiguous), "no_ambiguous_ids")}


def stability(old_ids, new_ids, lineage, old_output, new_output, *, ambiguous=()):
    if len(set(lineage.values())) != len(lineage) or not set(lineage) <= set(old_ids) or not set(lineage.values()) <= set(new_ids):
        raise ValueError("Lineage must be an explicit one-to-one map between declared snapshots")
    common = sorted(set(lineage) - set(ambiguous))
    if old_output["status"] != "completed" or new_output["status"] != "completed":
        return unavailable("failed_or_unsupported_comparison")
    if any(len(set(output.get("owners", {}).get(key, []))) > 1 for output, ids in ((old_output, common), (new_output, [lineage[k] for k in common])) for key in ids):
        return unavailable("conflicting_ownership")
    old = {k: v[0] for k, v in old_output["owners"].items() if len(v) == 1}
    new = {k: v[0] for k, v in new_output["owners"].items() if len(v) == 1}
    changed = sum(same_group(old, a, b) != same_group(new, lineage[a], lineage[b]) for a, b in combinations(common, 2))
    return rate(changed, len(common) * (len(common) - 1) // 2, "fewer_than_two_unchanged_ids")
