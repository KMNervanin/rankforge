# Before the blueprint — manifest contract v1

The recovered outpost needs a delivery service. Before choosing servers, separate what the operator promised from what you would like to assume. `ticket.json` is the versioned source of truth. It names an authorized actor, an operation, required payload fields, an inclusive quantity limit, restart persistence and a p95 latency target. Payments and multi-region operation are excluded. Dispatch policy is deliberately open: choose manual or automatic and acknowledge its consequence, or keep the question explicitly open.

## Your artifact

Implement `build_manifest(ticket)` in `manifest.py`. Return a dictionary in the shape below. This thin function allows the same manifest structure to be exercised after the ticket changes. The learning artifact is the requirements/case mapping, not an architecture generator. You may add a separate `RATIONALE.md`; it is optional and review-only.

```text
schema_version: 1
ticket_id, revision: copied from the supplied ticket
requirements: [{id: your unique nonempty string,
                facts: [{id: ticket fact ID, value: exact typed value, unit: exact unit}]}]
cases: [{id: your unique nonempty string, kind: published case kind,
         requirements: [your requirement IDs], assumptions: [ticket question IDs]}]
assumptions: [{question: ticket question ID, choice: option ID, source: "assumption"}]
open_questions: [ticket question IDs not yet decided]
exclusions: [every excluded scope ID from the ticket]
```

Each fact must occur exactly once across requirements, with its value and unit intact: the value keeps its exact type, so `25` is not `25.0`. Every requirement lists at least one fact. Group related facts into one requirement or separate them. Each required fact's `cases` kinds must be linked to the requirement containing that fact. For example, a quantity-limit requirement needs both `boundary` and `over_limit`: the first describes acceptance at the inclusive limit; the second describes rejection above it. `missing_field` observes input rejection, `unauthorized` denied access, `restart` retained acknowledged data, and `measurement` compares an observed p95 against the target. A case is a *planned observation*, not a claim that you executed a service.

For each question, either declare exactly one allowed assumption or put its ID in `open_questions`. An assumption also needs cases for its chosen option's published kinds, linked via `assumptions`. `operator_confirmation` observes waiting for approval; `automatic_dispatch` observes dispatch without approval. A case may cover multiple requirements/assumptions; lists have no duplicates and every reference must exist. A case must have at least one reference, and its kind must belong to every referenced requirement (union of its facts' kinds) or chosen assumption. Case and requirement IDs are separate namespaces. All required collections must be present, even when empty. Exclusions are unique and exactly match the ticket; they cannot be promoted into requirements. Unknown fact IDs and claimed `source: "fact"` assumptions fail.

Ordering and extra descriptive fields (such as `description` or `rationale`) are free. Their wording is never graded. No particular English phrase or case decomposition is required. Preserve the input and return the same manifest on repeat calls; do not read a fixed ticket from disk inside the function. Never change a manifest after returning it: Verify keeps every returned manifest and compares it again after later tickets, so build fresh lists and dictionaries for each call. Input tickets are valid v1 dictionaries in this published shape; malformed-ticket handling is outside the lab.

## Changes are part of the ticket

Verify supplies the original ticket and **two changed tickets**, plus fresh identifiers/limits. `ticket-v2.json` lowers the quantity limit and latency target. `ticket-v3.json` changes the actor, payload fields and excluded scope. The structure stays v1; requirements and case IDs may be your own. Never pretend the p95 target is a measured mean. These are delivery requirements, not evidence of server capacity.

## Start and investigate

From this workspace, save your file, then run:

```sh
python3 -B demo.py
python3 -B demo.py ticket.json
python3 -B demo.py ticket-v2.json
python3 -B demo.py ticket-v3.json
```

The starter intentionally prints empty requirements and cases. It is not a completed design. The demo prints your artifact; use **Verify lab** for the independent contract checks. Neither command overwrites files. The later guild missions carry their own copy of this briefing context; they do not silently copy or modify this workspace.

If Python collections are unfamiliar: a dictionary names a value (`ticket["revision"]`), a list holds several values, and `for fact in ticket["facts"]:` visits them. Build new lists/dictionaries instead of deleting from the input. A function returns data; printing alone is not a return value. No other lesson or installation is required before this mission.

## Boundary

Python standard library >=3.10; no service, downloads or network needed. Keep work in this directory and avoid import-time side effects. The checker verifies structured traceability to published facts, not prose quality, feasibility, architecture mastery or actual latency/persistence. Those claims need experiments and review later. The optional debrief never gates this artifact.
