"""Golden set as a GoldenSet object built from dataclass cases; the manifest dict is its serialized form."""
import bisect
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from itertools import combinations

SPLITS = ("train", "dev", "test")
PROVENANCE_KINDS = ("real", "synthetic")
NOT_ALNUM = re.compile(r"[^\w\s]|_")


def normalize_text(text):
    return re.sub(r"\s+", " ", NOT_ALNUM.sub(" ", str(text))).strip().casefold()


def case_hash(case):
    payload = {"id": case["id"], "input": case["input"], "expected": case["expected"], "category": case["category"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def assign_split(case_id, seed, split_ratios):
    position = int(hashlib.sha256(f"{seed}:{case_id}".encode("utf-8")).hexdigest()[:8], 16) / 2**32
    thresholds = [split_ratios["train"], split_ratios["train"] + split_ratios["dev"]]
    return SPLITS[bisect.bisect_right(thresholds, position)]


def held_out_digest(hashes):
    digest = hashlib.sha256()
    for index, item in enumerate(sorted(hashes)):
        if index:
            digest.update(b"\n")
        digest.update(item.encode("utf-8"))
    return digest.hexdigest()


@dataclass
class Case:
    id: str
    input: str
    expected: str
    category: str
    provenance: dict
    split: str = ""
    hash: str = ""

    @classmethod
    def parse(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("case: not an object")
        for key in ("id", "input", "expected", "category"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise ValueError(f"case: {raw.get('id', '?')} needs a non-empty string {key}")
        provenance = raw.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("kind") not in PROVENANCE_KINDS or not str(provenance.get("source") or "").strip():
            raise ValueError(f"provenance: {raw['id']} needs provenance {{kind: real|synthetic, source: note}}")
        return cls(raw["id"], raw["input"], raw["expected"], raw["category"], dict(provenance), raw.get("split", ""), raw.get("hash", ""))

    def stamped(self, seed, ratios):
        return Case(self.id, self.input, self.expected, self.category, dict(self.provenance), assign_split(self.id, seed, ratios), case_hash(asdict(self)))


@dataclass
class GoldenSet:
    version: int
    seed: str
    split_ratios: dict
    minimum_per_category: int
    cases: list = field(default_factory=list)
    history: list = field(default_factory=list)

    @staticmethod
    def check_ratios(ratios):
        if not isinstance(ratios, dict) or set(ratios) != set(SPLITS):
            raise ValueError("split_ratios needs exactly the keys train, dev and test")
        values = [float(ratios[name]) for name in SPLITS]
        if min(values) < 0 or abs(sum(values) - 1) > 1e-9:
            raise ValueError("split_ratios must be non-negative and sum to 1")
        return dict(zip(SPLITS, values))

    def counts(self):
        return {name: sum(1 for case in self.cases if case.split == name) for name in SPLITS}

    def categories(self):
        result = {}
        for case in self.cases:
            result[case.category] = result.get(case.category, 0) + 1
        return result

    def digest(self):
        return held_out_digest([case.hash for case in self.cases if case.split == "test"])

    def to_manifest(self):
        return {"version": self.version, "seed": self.seed, "split_ratios": dict(self.split_ratios), "minimum_per_category": self.minimum_per_category,
                "cases": [asdict(case) for case in self.cases], "counts": self.counts(), "categories": self.categories(),
                "held_out_digest": self.digest(), "history": [dict(entry) for entry in self.history]}

    @classmethod
    def from_manifest(cls, manifest):
        ratios = cls.check_ratios(manifest.get("split_ratios"))
        cases = [Case.parse(raw) for raw in manifest.get("cases") or []]
        ids = [case.id for case in cases]
        if len(set(ids)) != len(ids):
            raise ValueError("case: duplicate id")
        return cls(int(manifest["version"]), str(manifest["seed"]), ratios, int(manifest.get("minimum_per_category", 1)), cases, [dict(entry) for entry in manifest.get("history") or []])


def build_manifest(cases, *, minimum_per_category, split_ratios, seed, version=1):
    if not isinstance(minimum_per_category, int) or minimum_per_category < 1:
        raise ValueError("minimum_per_category must be a positive integer")
    if not isinstance(version, int) or version < 1:
        raise ValueError("version must be a positive integer")
    ratios = GoldenSet.check_ratios(split_ratios)
    parsed = [Case.parse(raw).stamped(str(seed), ratios) for raw in cases]
    if len({case.id for case in parsed}) != len(parsed):
        raise ValueError("case: duplicate id")
    golden = GoldenSet(version, str(seed), ratios, minimum_per_category, parsed)
    short = sorted(name for name, count in golden.categories().items() if count < minimum_per_category)
    if short:
        raise ValueError(f"category: {', '.join(short)} below the minimum of {minimum_per_category}")
    golden.history.append({"version": version, "action": "build", "case_ids": [case.id for case in parsed], "held_out_digest": golden.digest(), "note": ""})
    return golden.to_manifest()


def check_leakage(manifest, few_shot_examples):
    lookup = {}
    for case in manifest["cases"]:
        if case["split"] in ("dev", "test"):
            lookup.setdefault(normalize_text(case["input"]), []).append(case)
    leaks = []
    for index, example in enumerate(few_shot_examples):
        text = example["input"] if isinstance(example, dict) else example
        for case in lookup.get(normalize_text(text), []):
            leaks.append(f"few-shot example {index} matches {case['split']} case {case['id']}")
    return leaks


def add_case(manifest, case, *, note=""):
    golden = GoldenSet.from_manifest(manifest)
    parsed = Case.parse(case)
    if any(existing.id == parsed.id for existing in golden.cases):
        raise ValueError(f"case: duplicate id {parsed.id}")
    golden.cases.append(parsed.stamped(golden.seed, golden.split_ratios))
    golden.version += 1
    golden.history.append({"version": golden.version, "action": "add_case", "case_ids": [parsed.id], "held_out_digest": golden.digest(), "note": str(note)})
    return golden.to_manifest()


def verify_manifest(manifest):
    try:
        golden = GoldenSet.from_manifest(manifest)
    except (ValueError, KeyError, TypeError) as error:
        return [str(error) if str(error).split(":")[0] in ("case", "provenance") else f"ratios: {error}"]
    errors = []
    for name, count in sorted(golden.categories().items()):
        if count < golden.minimum_per_category:
            errors.append(f"category: {name} has {count} cases, minimum {golden.minimum_per_category}")
    for case in golden.cases:
        if case.hash != case_hash(asdict(case)):
            errors.append(f"hash: {case.id} does not match its content")
        expected = assign_split(case.id, golden.seed, golden.split_ratios)
        if case.split != expected:
            errors.append(f"split: {case.id} is in {case.split!r}, the seeded rule says {expected}")
    if manifest.get("counts") != golden.counts():
        errors.append(f"counts: recorded {manifest.get('counts')}, recounted {golden.counts()}")
    recomputed = held_out_digest([case_hash(asdict(case)) for case in golden.cases if case.split == "test"])
    if manifest.get("held_out_digest") != recomputed:
        errors.append(f"held_out: digest {manifest.get('held_out_digest')} does not match the test split, recomputed {recomputed}")
    last = golden.history[-1] if golden.history else {}
    if last.get("version") != golden.version or last.get("held_out_digest") != manifest.get("held_out_digest"):
        errors.append("history: the last entry must carry the manifest version and held-out digest")
    for left, right in combinations(golden.cases, 2):
        if normalize_text(left.input) == normalize_text(right.input):
            errors.append(f"duplicate: cases {left.id}, {right.id} share the same normalized input")
    return errors
