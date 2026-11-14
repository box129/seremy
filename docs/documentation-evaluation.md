# Documentation evaluation and human review

Run the corpus from the repository root.

```powershell
python -B -m seremy.evaluate_documentation --output test-results/documentation-evaluation
```

The command uses the real analysis, deterministic guide, publication, MapBridge section retrieval and draft-submission paths. It writes `EVALUATION.md`, `evaluation.json`, `REVIEW-PACK.md`, `review-template.json` and the source-bound guide/map/draft artifacts for each case. Each fixture is copied into a temporary directory before mutation. The original corpus stays intact.

## Corpus and scope

The Python fixture includes a direct cross-file call, a callback parameter, a FastAPI declaration/import and a misleading repository comment. The TSX fixture includes an aliased call, a component function call, a JSX tag and React declared without a source import. Separate same-named functions provide valid but irrelevant citation ranges. `seremy/fixtures/documentation-evaluation/truth.json` supplies handwritten expected source files, symbols, lines, tokens, non-bound outcomes and framework records.

The implementing agent authored both source and expected facts separately from generator output. Independent human adjudication remains pending. This bounded corpus provides regression and conformance evidence. Broader repository accuracy and model usefulness require additional evaluation. The draft lane uses an explicitly authored explanation fixture. The preceding real Codex/SDK example retains its separately recorded integration scope.

## Automated measures

The report counts passing cases, expected direct relationships, independently specified call/target citations, required section-topic presence and expected non-bound outcomes. It records distinct relationship/site scope and per-case precision. A failed analysis remains a failed case in the corpus denominator. Missing cases contribute zero to required-fact numerators. Required-topic presence measures the presence of populated sections.

The negative probes reverse a call, substitute a valid citation to an unrelated declaration, inject runtime/ownership prose and provide foreign snapshot/claim references. Additional probes alter graph data, membership, policy, actual call-target source and configuration. Source and configuration freshness are measured separately. Corrupt graph data is recorded as rejected by the bundle loader. Unsupported new prose submitted as an explanation keeps a review label; an altered factual projection is rejected.

Run identity binds the corpus hashes, evaluator hash, case outputs, document/graph identities, draft identities and measured results. Repeated successful runs are reproducible across temporary directories. Reviews bind the exact run digest.

## Review workflow

1. Open `REVIEW-PACK.md` and inspect each linked source range and surrounding source. Compare the entire statement with the evidence, including qualifications about static behavior and incomplete scope.
2. Copy `review-template.json` to a separate file such as `my-review.json`. Regeneration replaces generated templates. Keep completed judgments in the separate file.
3. Enter a reported reviewer identity and a timezone-bearing review timestamp. For each assessed unit, record support as supported, contradicted or insufficient. Record citation correctness as correct, incorrect or uncertain. Copy the actual checked citation objects into `evidence_checked` and explain judgments in `notes`.
4. Rate clarity and usefulness from 1 to 5 using the anchors in the review pack. Leave unassessed fields null.
5. Score that record against a fresh run of the same corpus and evaluator.

```powershell
python -B -m seremy.evaluate_documentation --output test-results/documentation-reviewed --reviews my-review.json
```

Review validation rejects foreign run IDs, unknown/duplicate units, invalid ratings, missing reviewer metadata and irrelevant evidence. The score reports only supplied judgment denominators and also reports review completion across all units. With no judgments, status stays `not_run`, support/citation denominators stay zero and quality means stay null. Reviewer identity and judgments remain self-reported, with semantic adjudication supplied by the reviewer.

Synthetic completed review records used in unit tests exercise scoring mechanics. Published evaluation receipts use the unfilled review template, with human factual support, clarity and usefulness pending.
