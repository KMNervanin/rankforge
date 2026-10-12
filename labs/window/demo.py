"""Terminal demo: python3 -B demo.py [window] [reserve_output] [overhead]

Reads context.json (instructions, pinned facts, documents and history for one
call), builds the messages for the given window with context.build and prints
them with the budget report. Defaults: window 1200, reserve 128, overhead 4.
Try a window of 700, then 350, and watch what the policy cuts first.
"""
import json
import sys

import context

if __name__ == "__main__":
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
    reserve = int(sys.argv[2]) if len(sys.argv) > 2 else 128
    overhead = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    with open("context.json", encoding="utf-8") as file:
        sections = json.load(file)["sections"]
    try:
        messages, report = context.build(sections, window=window, reserve_output=reserve, overhead=overhead)
    except context.BudgetError as error:
        sys.exit(f"BudgetError: {error}")
    for message in messages:
        print(f"--- {message['role']}")
        print(message["content"])
    print("--- report")
    print(json.dumps(report, indent=2, ensure_ascii=False))
