# Stage 5 membership interface

The opt-in Stage 5 contract exports structural baselines and experimental semantic, layer and role views. Each view records its observed-declaration universe, input binding, cut identity, hierarchy, map version, producer, supporting evidence and interpretation. The first executable adapter consumes authored records. A Python callback interface accepts candidate proposals under the same validator.

## Product entry point

First analyze the repository and inspect the graph for declaration IDs and captured input digests. Prepare a plan outside the repository input so the plan itself does not change that captured inventory. Supply it on the next analysis of the same inputs.

```powershell
python -B -m seremy analyze PATH_TO_REPOSITORY --output PATH_TO_BASELINE
python -B -m seremy analyze PATH_TO_REPOSITORY --membership-plan PATH_TO_PLAN_JSON --output PATH_TO_PUBLICATION
```

The Python API accepts `analyze(root, membership_plan=plan)`. Omitting the plan uses the existing structural graph. The complete stored Redux graph compares identically in the compatibility check. Existing snapshots retain their graph and saved-view identities.

A plan has exactly these top-level fields.

```json
{
  "profile": "seremy-membership-plan-v0.1",
  "producer": "my-authored-membership/0.1",
  "origin": "authored_contract",
  "binds": {},
  "scheduled_targets": ["semantic_component"],
  "execution": "completed",
  "diagnostics": [],
  "views": [],
  "role_views": []
}
```

Populate `binds` with `seremy.membership.input_binding(contents)` from the baseline graph. It includes repository/inventory identity, S02/S03/S04 digests and the policy digest. Origin is authored_contract, derived or model_hypothesis. A producer is a declared versioned identity. A failed attempt retains its scheduled targets and diagnostics with empty predictions.

Each proposed primary view supplies `view_id`, `target`, `rationale`, `groups`, `cut_id`, `cut`, `parents`, `assignments` and `disputed`. Targets are semantic_component or architectural_layer. Groups map unique IDs to names. Parents map a child group ID to one parent, forming a forest. The cut lists active ownership groups and forms an antichain in the hierarchy. An assignment has entity_id, group_id, evidence and interpretation. At most one primary owner may be assigned to an entity at a cut.

An assignment or dispute references its own observed entity as an evidence record. Additional witnesses may reference an observed edge ID, a content-bound UTF-8 source span, or an S02/S03/S04 artifact digest and record path. Source ranges reject foreign hashes, invalid boundaries and split UTF-8 characters. Artifact paths are arrays of dictionary keys or list indices. Membership interpretation retains support unassessed.

Disputes have entity_id, two or more candidate group IDs, reason and evidence. Disputed entities stay unassigned. The unassigned count includes disputes, so assigned plus unassigned equals the eligible observed universe. Empty candidate output retains unassignment and zero predicted groups. Files with no observed declarations, including failed/unreadable inputs, remain in the file universe and upstream coverage.

## Roles, alternatives and hierarchy

Overlapping roles use the separate role_views roster with target role. An entity may carry several role groups. Role relationships have an explicit not_applicable result until role-specific relationship semantics are defined. Primary semantic/layer partitions retain their separate ownership maps.

Optional alternative_set IDs keep complete alternative views together. Alternatives share target, universe and cut identity. Each retains its complete mapping, rationale and uncertainty. Assignment coverage and group naming remain separate records. Parent group membership aggregates declared descendants with deduplicated entity IDs. Cycles and parent/child groups in the same primary cut fail validation.

## Candidate adapter

```python
from seremy.membership import candidate_plan

plan = candidate_plan(contents, "candidate-rule/0.1", adapter)
```

The callback receives a deep copy of captured upstream snapshot, inventory, S02/S03/S04, coverage, source and policy inputs. It returns a list of proposed primary views. Existing S05/S06 interpretations are outside this input roster. The wrapper records derived origin by default. A model-backed proposal can declare model_hypothesis. Callback exceptions and invalid output become failed attempts with diagnostics. Candidate output passes the same product validator as authored input. This interface provides controlled mechanics before algorithm selection.

## Consumer behavior and scope

The optional S05 experimental_membership artifact retains both the plan and normalized output. S06 exports corresponding relationship views with membership lineage, source-edge IDs, distinct-edge counts and occurrence counts. Edges with unassigned endpoints remain in an explicit list. Source-call facts keep their existing S03 origin. Boundary policy checks use the default structural view.

Documentation adds a labelled experimental section. The map's Coverage panel exposes assignments, disputes, input coverage and evidence. The source canvas continues to show source files and observed calls. MCP selection context supplies the experimental artifact, and section reads expose the generated documentation. An invalid or stale plan fails before a new publication pointer is installed.

For local MCP access to a CLI-generated report, start `python -B -m seremy.server --output PATH_TO_PUBLICATION` and open `/reports/PUBLICATION_ID/map.html` on that launcher's address. Use the published directory's hexadecimal ID. Enable Share selection with agent in Inspect, then use the existing MCP connection and view/digest selection workflow.

The authored mechanics fixture covers shared infrastructure, cross-group coupling, isolated declarations, ambiguous adapter ownership, empty files and failed parsing. Browser checks cover SVG/Pixi navigation and saved views. The complete default Redux graph matches the stored pre-membership object. Semantic algorithm accuracy, historical F09/F12 ownership and F11 equivalence adjudication, and lineage-aware comparison remain separate qualification work. Experimental quality assessment stays not_run.
