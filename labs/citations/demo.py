"""Terminal demo: python3 -B demo.py ["a question"] | --conflict | --empty

Reads llm.json (endpoint and model, no secrets) and passages.json, then runs answer on every
question in questions.json, or on the question given as an argument, and prints the result with a
faithfulness report from a stand-in judge that counts a claim as supported when it shares three
words with a cited passage (the calibrated judge of the previous mission replaces it in real use).
--conflict answers from versions.json, where two versions of the relay runbook disagree;
--empty asks with no passages at all.
"""
import json
import sys

import answer


def word_overlap_judge(claim, passages):
    words = {word.strip(".,;:!?\"'").casefold() for word in claim.split() if len(word) > 3}
    return any(len(words & {word.strip(".,;:!?\"'").casefold() for word in passage["text"].split()}) >= 3 for passage in passages)


if __name__ == "__main__":
    arguments = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    with open("llm.json", encoding="utf-8") as file:
        endpoint = json.load(file)
    if not endpoint["model"]:
        sys.exit("Set the model id in llm.json first (for Ollama: the name shown by `ollama list`).")
    source = "versions.json" if "--conflict" in sys.argv else "passages.json"
    with open(source, encoding="utf-8") as file:
        passages = [] if "--empty" in sys.argv else json.load(file)
    if arguments:
        questions = [" ".join(arguments)]
    elif "--conflict" in sys.argv or "--empty" in sys.argv:
        questions = ["How long should the operator wait after switching relay 4 off?"]
    else:
        with open("questions.json", encoding="utf-8") as file:
            questions = [fixture["question"] for fixture in json.load(file)]
    print(f"conflicts: {json.dumps(answer.reconcile(passages))}")
    for question in questions:
        result = answer.answer(question, passages, base_url=endpoint["base_url"], model=endpoint["model"], max_tokens=int(endpoint.get("max_tokens", 400)))
        print(f"--- {question}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("faithfulness:", json.dumps(answer.faithfulness(result, passages, word_overlap_judge)))
