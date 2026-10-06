import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capacity import estimate

if __name__ == "__main__":
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("workload.json")
    try:
        result = estimate(json.loads(source.read_text()))
        print(json.dumps(result, indent=2, default=str))
    except ValueError as error:
        print(f"Invalid workload: {error}", file=sys.stderr)
        sys.exit(1)
