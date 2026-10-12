"""Terminal demo for the prompt registry.

  python3 -B demo.py verify
  python3 -B demo.py render triage v2 "Need 40 water filters for outpost 3."
  python3 -B demo.py call triage v2 "Need 40 water filters." --base-url http://127.0.0.1:11434/v1 --model <id>
  python3 -B demo.py replay 1          # re-render the first line of usage.log and compare hashes

`call` needs an OpenAI-compatible endpoint; a local server such as Ollama needs no key. If your
endpoint needs one, put it in the environment variable LLM_API_KEY, never in a file here.
"""
import argparse
import json
import sys

from registry import Registry, RegistryError

ROOT = "templates"
LOG = "usage.log"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify")
    for name in ("render", "call"):
        command = sub.add_parser(name)
        command.add_argument("name")
        command.add_argument("version")
        command.add_argument("text", help="the operator's request; a second value, if the template needs one, follows as key=value")
        command.add_argument("extra", nargs="*", help="further variables as key=value")
        if name == "call":
            command.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
            command.add_argument("--model", required=True)
            command.add_argument("--max-tokens", type=int, default=16)
            command.add_argument("--temperature", type=float, default=0.0)
    replay = sub.add_parser("replay")
    replay.add_argument("line", type=int, help="1-based line number in usage.log")
    args = parser.parse_args()
    registry = Registry(ROOT)
    try:
        if args.command == "verify":
            print(json.dumps(registry.verify(), indent=2))
            return
        if args.command == "replay":
            with open(LOG, encoding="utf-8") as handle:
                record = json.loads(handle.read().splitlines()[args.line - 1])
            print(registry.replay(record))
            return
        variables = {"request": args.text}
        for item in args.extra:
            key, _, value = item.partition("=")
            variables[key] = value
        if args.command == "render":
            print(registry.render(args.name, args.version, variables))
            return
        record = registry.call(args.name, args.version, variables, base_url=args.base_url, model=args.model,
                               params={"max_tokens": args.max_tokens, "temperature": args.temperature}, log_path=LOG)
        print(json.dumps(record, indent=2, ensure_ascii=False))
    except RegistryError as error:
        sys.exit(f"registry error: {error}")


if __name__ == "__main__":
    main()
