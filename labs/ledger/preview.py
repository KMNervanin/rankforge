import json
from transform import transform

rows = [
    {"id": "a", "date": "2026/02/10", "amount": "0.10"},
    {"id": "b", "date": "2026-02-10", "amount": "0.20"},
    {"id": "a", "date": "2026/02/10", "amount": "0.10"},
]
print(json.dumps(transform(rows), indent=2))
