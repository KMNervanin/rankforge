"""Terminal workbench: python3 -B demo.py next | show <trace_id> | report | transfer

next      prints the first trace in traces.jsonl that annotations.jsonl does not cover yet.
show ID   prints one trace with its passages, tool calls and answer.
report    builds the taxonomy from annotations.jsonl with the definitions of taxonomy.json,
          prints the counts and every inconsistency reconcile finds against taxonomy.json.
transfer  reads fresh-annotations.jsonl (your reading of fresh.jsonl) and prints which categories recur.
"""
import json
import os
import sys

import taxonomy

HERE = os.path.dirname(os.path.abspath(__file__))


def read_traces(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def show(trace):
    print(f"=== {trace['trace_id']}  (finish_reason: {trace['finish_reason']})")
    print(f"request:  {trace['request']}")
    for passage in trace["passages"]:
        print(f"passage:  [{passage['source']}] {passage['title']}: {passage['text']}")
    for call in trace["tool_calls"]:
        print(f"tool:     {call['tool']}({json.dumps(call['arguments'])}) -> {json.dumps(call['result'])}")
    print(f"answer:   {trace['answer']}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "next"
    annotations_path = os.path.join(HERE, "annotations.jsonl")
    annotations = taxonomy.load_annotations(annotations_path) if os.path.exists(annotations_path) else []
    if command == "next":
        seen = {record["trace_id"] for record in annotations}
        pending = [trace for trace in read_traces("traces.jsonl") if trace["trace_id"] not in seen]
        print(f"{len(seen)} annotated, {len(pending)} to go")
        if pending:
            show(pending[0])
    elif command == "show":
        for trace in read_traces("traces.jsonl") + read_traces("fresh.jsonl"):
            if trace["trace_id"] == sys.argv[2]:
                show(trace)
    elif command == "report":
        with open(os.path.join(HERE, "taxonomy.json"), encoding="utf-8") as file:
            published = json.load(file)
        definitions = {category["name"]: category["definition"] for category in published["categories"]}
        built = taxonomy.build_taxonomy(annotations, definitions)
        print(f"{built['total']} annotated, {built['passes']} pass")
        for category in built["categories"]:
            print(f"  {category['count']:3d}  {category['name']}  e.g. {', '.join(category['trace_ids'][:3])}")
        problems = taxonomy.reconcile(annotations, published)
        print("taxonomy.json reconciles with annotations.jsonl" if not problems else "\n".join(f"- {problem}" for problem in problems))
    elif command == "transfer":
        with open(os.path.join(HERE, "taxonomy.json"), encoding="utf-8") as file:
            published = json.load(file)
        fresh_path = os.path.join(HERE, "fresh-annotations.jsonl")
        if not os.path.exists(fresh_path):
            sys.exit("Annotate fresh.jsonl into fresh-annotations.jsonl first (same format as annotations.jsonl).")
        fresh = taxonomy.load_annotations(fresh_path)
        print(json.dumps(taxonomy.recurrence(published, fresh), indent=2))
    else:
        sys.exit(__doc__)
