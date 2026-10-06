import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest import build_manifest

if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("ticket.json")
    print(json.dumps(build_manifest(json.loads(source.read_text())), indent=2))
