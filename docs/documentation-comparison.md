# Documentation comparison and follow-up

On 15 November 2026 I interacted with SEREMY and DeepWiki using Redux. DeepWiki is the closest comparison for repository-generated developer documentation. This inspection does not establish a universal best documentation product.

I opened DeepWiki's Redux overview and Store API page, then submitted the same question used in SEREMY's live test about the checks in `isAction`. DeepWiki returned a structured answer with source and test excerpts, examples, related API context and related pages. Its persistent wiki also provides a hierarchy of conceptual and API pages. [Redux overview](https://deepwiki.com/reduxjs/redux), [Store API](https://deepwiki.com/reduxjs/redux/2.1-store-api), [matching question](https://deepwiki.com/search/0126a029-3eb3-413d-9fc7-9ecfd041ce47?mode=fast)

## Findings

| Area | SEREMY before this follow-up | DeepWiki observed behavior | Follow-up |
| --- | --- | --- | --- |
| Analysis feedback | Status text without a percent bar | An already indexed repository was inspected | Add progress bars driven by worker milestones in the dialog and workspace |
| First visible generated result | Short answer appended below the structural guide | Standalone wiki pages and a separate question response | Open the selected generated document directly, with a document picker |
| Writing | One to three short explanatory statements in the live checks | Sections, API descriptions, examples and integration context | Request a coherent page with purpose, interface, flow, dependencies, an illustrative example and limits |
| Evidence acquisition | First 20 matching claims and bounded bodies | Citations to source, existing documentation and tests | Further work is required for broad, question-aware retrieval and captured documentation inputs |
| Repository-wide coverage | Structural guide plus separately requested drafts | Hierarchical conceptual and API pages | Further work is required for a planned multi-page wiki and cross-page links |
| Diagrams | Source map is separate from documentation | Conceptual and lifecycle diagrams on wiki pages | Further work is required for evidence-backed diagrams within documents |

The scopes differ. DeepWiki's indexed Redux version was `28d433b7` from 23 June 2026 and its pages use README, docs and tests. SEREMY's live example analyzed the newer `src` subtree. This is a feature and user-experience comparison, with different source scope and versions. It is not a matched extraction-accuracy benchmark.

## Implemented changes

The analysis worker publishes milestone percentages through an atomic progress file. Both local and hosted jobs report those milestones. The UI shows a loading line, percent and current stage. The percentages represent stage milestones, with 100 reserved for successful publication. They are independent of elapsed time, and stages can be skipped visually on fast analyses. Failures and cancellations retain their last completed progress.

Generated drafts open as individual documents. The document picker switches between the architecture guide and each generated page. The model prompt requests 5â€“7 Markdown sections with source support and roughly 350â€“650 words, scaled to the source. The existing 2,048-token ceiling and model settings remain in force, so actual document length can vary. The validator still checks evidence identities and retains human review labels. Prompt version `hosted-documentation-v2` identifies this change.

## Remaining work toward a repository wiki

1. Capture and cite relevant README, existing docs, manifests and tests alongside source while preserving snapshot identity and clear source-type labels.
2. Retrieve source and neighboring declarations by the requested topic, paginate larger scopes and expand truncated bodies before drafting.
3. Plan pages for repository overview, components, important flows, interfaces and contributor workflows, then generate and navigate those pages as a set.
4. Add examples checked against observed signatures, evidence-backed diagrams and checks for unsupported prose claims.

These remaining items require implementation and evaluation. The current page and progress changes improve the existing product but leave those wiki capabilities open.


## Follow-up on reader goals

Overview and walkthrough generation now have separate prompts and a page selector. Scoped retrieval includes captured static dependencies and consumers. Topic terms, entry filenames and import frequency order files, with one evidence-bearing claim per file before additional claims. Body retrieval distributes the eight available ranges across files before returning to additional declarations in the same file. Generated pages retain source links, review notices, document selection and device saving.

This is a bounded first implementation of topic-aware retrieval. It does not complete the remaining repository-wiki items above. In particular, existing prose documentation ingestion and automatic wiki planning still need implementation.
