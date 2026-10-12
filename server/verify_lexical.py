"""Lexical versus dense retrieval checks for the Lexical mission; run outside the learner workspace.

Nothing here calls a model. The dense side uses Verify's own embed stand-in: a hashed bag of words
with a small thesaurus, normalized, deterministic and labeled as a test tool. Verify recomputes every
dense ranking by cosine from those vectors and every recall@k with Fraction from the rankings the
learner's report carries; the lexical expectations are hand-derived from term frequency and length.
"""
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
from fractions import Fraction

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
K = 3
TOLERANCE = Fraction(1, 10**9)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Rankings and the per-category report verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


def fts5_available():
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
        return True
    except sqlite3.OperationalError:
        return False


# Verify's embed stand-in: whitespace chunks with a digit (part numbers, error codes, times) are
# dropped, words are crudely stemmed and mapped through a thesaurus, then hashed into 64 buckets.
STOP = {"the", "a", "an", "of", "on", "in", "at", "to", "for", "and", "is", "are", "it", "its", "be", "was", "from", "with", "by", "that", "this", "after", "before", "then", "who", "can", "how", "off", "out", "made", "may", "only", "until"}
THESAURUS = {
    "outage": "brownout", "blackout": "brownout", "dip": "brownout", "power": "relay", "bring": "restart", "back": "restart",
    "inventory": "stock", "number": "count", "sign": "approve", "order": "reservation", "booking": "reservation", "above": "exceed",
    "cartridge": "filter", "burnt": "blown", "date": "stale", "ledger": "stock",
}


def stem(word):
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def embed(text):
    cleaned = re.sub(r"\S*\d\S*", " ", text.lower())
    vector = [0.0] * 64
    for word in re.findall(r"[a-z]+", cleaned):
        if word in STOP:
            continue
        canonical = THESAURUS.get(stem(word), stem(word))
        bucket = int(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), 16) % 64
        vector[bucket] += 1.0
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def fresh():
    rng = random.Random()
    return {
        "part": f"FLT-{rng.randint(100, 999)}{rng.choice('ABCD')}",
        "error": f"E{rng.randint(100, 999):04d}",
        "board": f"RB/{rng.randint(1000, 9999)}-{rng.choice('KLMN')}",
        "bay": rng.randint(11, 99),
    }


def passages(values):
    part, error, board, bay = values["part"], values["error"], values["board"], values["bay"]
    return [
        {"id": "p01", "text": "The relay brownout at 02:10 lasted eleven minutes; stock queries returned stale counts until the cache lease expired."},
        {"id": "p02", "text": "Spare gaskets are kept in bay nine behind the clamps."},
        {"id": "p03", "text": "Behind the clamps in bay nine are the spare gaskets kept."},
        {"id": "p04", "text": f"The FLT line of intake filters shares bay {bay} with gasket kit {part[4:]} and the clamps."},
        {"id": "p05", "text": "Fuse drawer: slow fuse, fast fuse and the fuse for the pump are counted weekly."},
        {"id": "p06", "text": f"Filter cartridge {part} fits the cold store intake and must be counted before every reservation."},
        {"id": "p07", "text": "A blown fuse on the intake pump is replaced from the drawer and logged in the incident report for the shift."},
        {"id": "p08", "text": f"Error {error} means the relay rejected a reservation because the operator lacks the outpost permission."},
        {"id": "p09", "text": "During the winter audit the quartermaster found one fuse missing from the drawer, two gaskets past their date, three runbooks with outdated contacts and a reservation ledger that nobody had signed for a month."},
        {"id": "p10", "text": "Only the quartermaster may approve a reservation that exceeds the counted stock; the request is refused and logged."},
        {"id": "p11", "text": "The relay runbook covers restarting the relay after a brownout: wait sixty seconds, then clear the cache."},
        {"id": "p12", "text": f"Relay board {board} replaces the burnt controller in the relay rack; order it through the depot."},
        {"id": "p13", "text": f"The RB depot shipment {board[3:7]} arrived with {board[-1]}-type clamps and a signed ledger."},
    ]


def queries(values):
    part, error = values["part"], values["error"]
    return [
        {"id": "q1", "category": "exact_code", "query": part, "expected": ["p06"]},
        {"id": "q2", "category": "exact_code", "query": error.lower(), "expected": ["p08"]},
        {"id": "q3", "category": "exact_code", "query": part.lower(), "expected": ["p06"]},
        {"id": "q4", "category": "paraphrase", "query": "power dip made the inventory numbers out of date", "expected": ["p01"]},
        {"id": "q5", "category": "paraphrase", "query": "how to bring the relay back after an outage", "expected": ["p11"]},
        {"id": "q6", "category": "paraphrase", "query": "who can sign off on an order above the counted inventory", "expected": ["p10"]},
        {"id": "q7", "category": "synonym", "query": "relay outage", "expected": ["p01", "p11"]},
        {"id": "q8", "category": "synonym", "query": "cartridge count before booking", "expected": ["p06"]},
    ]


def dense_expected(corpus, query, k):
    vector = embed(query)
    scored = [(passage["id"], cosine(vector, embed(passage["text"]))) for passage in corpus]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored[:k]


def recall(expected, ranked):
    return Fraction(len(set(expected) & set(ranked)), len(set(expected)))


def close(value, wanted):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and abs(Fraction(str(value)) - wanted) <= TOLERANCE


def trial():
    require(MISSION == "lexical", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_lexical", os.path.join(WORKSPACE, "lexical.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load lexical.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("tokenize", "build_index", "search_lexical", "search_dense", "evaluate", "compare"):
        require(callable(getattr(candidate, name, None)), f"lexical.py must define {name}(...)")
    require(isinstance(getattr(candidate, "CODE_PATTERNS", None), list) and candidate.CODE_PATTERNS, "lexical.py must publish CODE_PATTERNS, a non-empty list of regular expressions")

    values = fresh()
    corpus, suite = passages(values), queries(values)
    part, error, board = values["part"], values["error"], values["board"]
    by_id = {passage["id"]: passage["text"] for passage in corpus}
    path = os.path.join(WORKSPACE, ".verify-lexical.sqlite")
    transfer_path = os.path.join(WORKSPACE, ".verify-transfer.sqlite")
    for stale in (path, transfer_path):
        if os.path.exists(stale):
            os.remove(stale)
    count = candidate.build_index(corpus, path)
    require(count == len(corpus), f"build_index must return the number of indexed passages ({len(corpus)}), got {count!r}")

    def tokenizer():
        tokens = candidate.tokenize(f"Replace {part} before {error} recurs.")
        require(tokens == ["replace", part.lower(), "before", error.lower(), "recurs"], f"tokenize must keep {part} and {error} whole and lowercase everything: got {tokens!r}")
        require(candidate.tokenize(part.lower()) == [part.lower()], f"A lowercase {part.lower()} is the same token as {part}")
        require(candidate.tokenize(f"kit {part[4:]} and the FLT line") == ["kit", part[4:].lower(), "and", "the", "flt", "line"], "Pieces of a code that stand alone are ordinary words")
        extra = candidate.tokenize(f"board {board} spare", code_patterns=list(candidate.CODE_PATTERNS) + [r"[A-Z]{2}/\d{4}-[A-Z]"])
        require(extra == ["board", board.lower(), "spare"], f"A pattern passed in code_patterns must apply: got {extra!r}")
        default = candidate.tokenize(f"board {board} spare")
        require(board.lower() not in default or len(default) == 3, "Without its pattern the new format is split into pieces or, if your own pattern already covers it, kept whole")
        return f"{part}, {error} and {board} tokenized as published; case folded."
    check("Tokenizer keeps part numbers and error codes as one token and folds case", tokenizer)

    def exact_codes():
        for query, target in ((part, "p06"), (part.lower(), "p06"), (error.lower(), "p08"), (error, "p08")):
            ranked = candidate.search_lexical(path, query, K)
            require(isinstance(ranked, list) and all(isinstance(pid, str) for pid in ranked), f"search_lexical must return a list of passage ids, got {ranked!r}")
            require(target in ranked, f"Query {query!r} must retrieve {target} (the only passage carrying the code); got {ranked!r}")
            require(ranked == [target], f"Query {query!r} must return only passages that carry the code as one token; got {ranked!r}. A tokenizer that splits {part} into pieces also matches p04.")
        return f"{part} and {error} retrieved exactly in both casings; the piece-wise decoy p04 stayed out."
    check("Exact-code queries hit on the lexical side: only passages carrying the code are returned", exact_codes)

    def ordering():
        # 'fuse': p05 four times in a short passage, p07 once in a medium one, p09 once in the longest. BM25 is monotone in tf and
        # decreasing in length, so ascending rank is p05, p07, p09 under any idf; a descending sort returns the weakest first.
        ranked = candidate.search_lexical(path, "fuse", K)
        require(ranked == ["p05", "p07", "p09"], f"'fuse' must rank the passage with four occurrences first and the longest single-mention passage last: expected ['p05', 'p07', 'p09'], got {ranked!r}")
        ranked = candidate.search_lexical(path, "spare gaskets", K)
        require(ranked == ["p02", "p03", "p09"], f"'spare gaskets' must rank the two passages with both terms first (identical scores, lower id first) and the single-term passage last: expected ['p02', 'p03', 'p09'], got {ranked!r}. Any-token matching and ORDER BY rank, id.")
        require(candidate.search_lexical(path, "fuse", 2) == ["p05", "p07"], "k limits the lexical result")
        require(candidate.search_lexical(path, "GASKET", K) == ["p04"], "Tokens are compared exactly after case folding: no stemming, 'gasket' is not 'gaskets'")
        return "Ascending bm25 confirmed on a single-term and a two-term query; equal scores fall to the lower id."
    check("Lexical ranking is ascending by bm25: the strongest match comes first and ties fall to the lower id", ordering)

    def dense():
        for query in ("spare gaskets bay", "stale counts after a power dip", part, "quartermaster approves"):
            wanted = [pid for pid, _ in dense_expected(corpus, query, K)]
            ranked = candidate.search_dense(path, query, K, embed)
            require(ranked == wanted, f"search_dense({query!r}) must return the top-{K} by cosine over the injected vectors, ties on the lower id: expected {wanted!r}, got {ranked!r}")
        require(candidate.search_dense(path, "spare gaskets bay", 2, embed) == ["p02", "p03"], "p02 and p03 embed to identical vectors: the tie falls to the lower id and k limits the list")
        return "Four dense rankings recomputed by cosine, including an exact tie and a zero query vector."
    check("Dense ranking recomputes by cosine over the injected vectors with the published tie rule", dense)

    def report_check():
        report = candidate.evaluate(path, suite, K, embed)
        require(isinstance(report, dict), "evaluate must return a dict report")
        require(report.get("k") == K, f"report['k'] must be {K}")
        entries = report.get("queries")
        require(isinstance(entries, list) and len(entries) == len(suite), f"report['queries'] must carry one entry per query ({len(suite)})")
        groups = {}
        for query, entry in zip(suite, entries):
            require(isinstance(entry, dict) and entry.get("id") == query["id"] and entry.get("category") == query["category"], f"Entry for {query['id']} must carry id and category")
            require(entry.get("expected") == query["expected"], f"Entry {query['id']} must carry the expected ids verbatim")
            for side in ("lexical", "dense"):
                ranked = entry.get(side)
                require(isinstance(ranked, list) and len(ranked) <= K and all(pid in by_id for pid in ranked) and len(set(ranked)) == len(ranked), f"Entry {query['id']}: {side} must be a list of at most {K} distinct passage ids, got {ranked!r}")
                require(close(entry.get(f"{side}_recall"), recall(query["expected"], ranked)), f"Entry {query['id']}: {side}_recall must be |expected ∩ ranked| / |expected| = {recall(query['expected'], ranked)} from the ranking in the entry, got {entry.get(f'{side}_recall')!r}")
            require(len(entry["dense"]) == K, f"Entry {query['id']}: the dense ranking always has k={K} ids")
            require(entry["dense"] == [pid for pid, _ in dense_expected(corpus, query["query"], K)], f"Entry {query['id']}: the dense ranking must be the cosine top-{K}")
            groups.setdefault(query["category"], []).append(entry)
        categories = report.get("categories")
        require(isinstance(categories, dict) and set(categories) == set(groups), f"report['categories'] must have exactly the categories of the queries {sorted(groups)}; one aggregate number hides them. Got {sorted(categories) if isinstance(categories, dict) else categories!r}")
        for name, group in groups.items():
            summary = categories[name]
            require(isinstance(summary, dict) and summary.get("queries") == len(group), f"categories[{name!r}]['queries'] must be {len(group)}")
            for side in ("lexical", "dense"):
                wanted = sum(recall(entry["expected"], entry[side]) for entry in group) / len(group)
                require(close(summary.get(f"{side}_recall"), wanted), f"categories[{name!r}]['{side}_recall'] must be the mean recall@{K} over its {len(group)} queries = {wanted} ({float(wanted):.6f}), got {summary.get(f'{side}_recall')!r}")
        overall = report.get("overall")
        require(isinstance(overall, dict) and overall.get("queries") == len(suite), f"report['overall']['queries'] must be {len(suite)}")
        for side in ("lexical", "dense"):
            wanted = sum(recall(entry["expected"], entry[side]) for entry in entries) / len(entries)
            require(close(overall.get(f"{side}_recall"), wanted), f"overall['{side}_recall'] must be the mean over all {len(suite)} queries = {wanted}, got {overall.get(f'{side}_recall')!r}")
        require(close(categories["exact_code"]["lexical_recall"], Fraction(1)), f"Every exact-code query must hit lexically: exact_code lexical_recall {categories['exact_code']['lexical_recall']!r}")
        require(close(categories["exact_code"]["dense_recall"], Fraction(0)), "With Verify's vectors, which drop codes, no exact-code query can hit on the dense side")
        verdict = candidate.compare(report)
        require(isinstance(verdict, dict) and set(verdict) >= set(groups), f"compare must name a winner per category, got {verdict!r}")
        for name, group in groups.items():
            lexical = sum(recall(entry["expected"], entry["lexical"]) for entry in group)
            dense_total = sum(recall(entry["expected"], entry["dense"]) for entry in group)
            wanted = "tie" if lexical == dense_total else ("lexical" if lexical > dense_total else "dense")
            require(verdict.get(name) == wanted, f"compare[{name!r}] must be {wanted!r} from the report's numbers, got {verdict.get(name)!r}")
        lines = [f"{name}: lexical {float(categories[name]['lexical_recall']):.2f}, dense {float(categories[name]['dense_recall']):.2f} → {verdict[name]}" for name in groups]
        trial.report = report
        return "; ".join(lines) + "."
    trial.report = None
    check("Per-category recall@k recomputes from the rankings in the report; one aggregate number is not enough", report_check)

    def compare_hand():
        hand = {"k": 2, "queries": [], "categories": {
            "exact_code": {"queries": 3, "lexical_recall": 1.0, "dense_recall": 1 / 3},
            "paraphrase": {"queries": 3, "lexical_recall": 1 / 3, "dense_recall": 1.0},
            "synonym": {"queries": 2, "lexical_recall": 0.75, "dense_recall": 0.75},
        }, "overall": {"queries": 8, "lexical_recall": 0.6875, "dense_recall": 0.6875}}
        verdict = candidate.compare(hand)
        require(isinstance(verdict, dict), "compare must return a dict")
        require(verdict.get("exact_code") == "lexical" and verdict.get("paraphrase") == "dense" and verdict.get("synonym") == "tie", f"Expected exact_code: lexical, paraphrase: dense, synonym: tie; got {verdict!r}")
        return "Hand-built report: lexical wins codes, dense wins paraphrases, synonyms tie."
    check("compare names the winner per category from the report's own numbers", compare_hand)

    def transfer():
        # Probes avoid p12 and p13: a passage carrying the new format gets shorter once the code is one token, which BM25 sees.
        before = {query: candidate.search_lexical(path, query, K) for query in (part, error.lower(), "fuse", "spare gaskets", "gasket kit")}
        patterns = list(candidate.CODE_PATTERNS) + [r"[A-Z]{2}/\d{4}-[A-Z]"]
        count = candidate.build_index(corpus, transfer_path, code_patterns=patterns)
        require(count == len(corpus), "build_index with code_patterns must index every passage")
        for query in (board, board.lower()):
            ranked = candidate.search_lexical(transfer_path, query, K)
            require(ranked == ["p12"], f"With the new pattern stored in the index, {query!r} must retrieve only p12; got {ranked!r} (p13 carries the pieces {board[3:7]} and {board[-1]} separately)")
        for query, wanted in before.items():
            ranked = candidate.search_lexical(transfer_path, query, K)
            require(ranked == wanted, f"The new pattern must not change other queries: {query!r} gave {ranked!r} in the new index, {wanted!r} before")
        return f"{board} retrieved exactly after one pattern was added; five queries that do not touch the new format unchanged."
    check("Transfer: a new code format in the pattern list is retrieved exactly and leaves other queries unchanged", transfer)

    def fresh_process():
        script = (
            "import importlib.util, json, sys\n"
            "spec = importlib.util.spec_from_file_location('candidate_fresh', sys.argv[1])\n"
            "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
            "queries = json.loads(sys.argv[3])\n"
            "print(json.dumps({'lexical': [module.search_lexical(sys.argv[2], query, 3) for query in queries],\n"
            "                  'transfer': module.search_lexical(sys.argv[4], sys.argv[5], 3)}))\n"
        )
        require(os.path.exists(path) and os.path.exists(transfer_path), "build_index must create the index file at path; an index kept in memory cannot be reopened")
        probes = [part, "fuse", "spare gaskets"]
        wanted = [candidate.search_lexical(path, query, K) for query in probes]
        wanted_transfer = candidate.search_lexical(transfer_path, board.lower(), K)
        completed = subprocess.run([sys.executable, "-I", "-B", "-c", script, os.path.join(WORKSPACE, "lexical.py"), path, json.dumps(probes), transfer_path, board.lower()], capture_output=True, text=True, timeout=20)
        require(completed.returncode == 0, f"A fresh process could not search the index: {completed.stderr[-600:]}")
        answer = json.loads(completed.stdout.strip().splitlines()[-1])
        require(answer["lexical"] == wanted, f"A fresh process must answer the same rankings from the file: got {answer['lexical']!r}, expected {wanted!r}")
        require(answer["transfer"] == wanted_transfer, f"The pattern list stored with the index must survive a reopen: a fresh process answered {answer['transfer']!r} for {board.lower()!r}, this process {wanted_transfer!r}")
        return "A separate Python process reopened both index files and answered the same rankings."
    check("The index at path answers the same rankings from a fresh process", fresh_process)

    def scored():
        report = trial.report
        require(isinstance(report, dict), "The report check must pass first")
        for query, entry in zip(suite, report["queries"]):
            for side in ("lexical", "dense"):
                pairs = entry.get(f"{side}_scored")
                require(isinstance(pairs, list) and [pair[0] for pair in pairs] == entry[side], f"Entry {query['id']}: {side}_scored must list [id, score] in the ranking's order")
                scores = [pair[1] for pair in pairs]
                require(all(isinstance(score, (int, float)) and 0.0 - 1e-9 <= score <= 1.0 + 1e-9 for score in scores), f"Entry {query['id']}: {side} scores must lie in [0, 1]")
                require(not scores or close(scores[0], Fraction(1)), f"Entry {query['id']}: the best {side} score is 1")
                require(all(a >= b - 1e-9 for a, b in zip(scores, scores[1:])), f"Entry {query['id']}: {side} scores are non-increasing")
                if len(scores) > 1 and len(set(scores)) > 1:
                    require(close(scores[-1], Fraction(0)), f"Entry {query['id']}: the worst {side} score is 0 unless every score is equal")
            cosines = [score for _, score in dense_expected(corpus, query["query"], K)]
            top, bottom = max(cosines), min(cosines)
            wanted = [1.0] * len(cosines) if top == bottom else [(value - bottom) / (top - bottom) for value in cosines]
            for pair, value in zip(entry["dense_scored"], wanted):
                require(abs(pair[1] - value) <= 1e-9, f"Entry {query['id']}: dense scores must be min-max normalized cosines within the list, got {pair[1]!r}, expected {value!r}")
        return "Both rankings carry min-max normalized scores per query; dense scores recomputed from Verify's cosines."
    check("bonus: both rankings carry scores normalized to [0, 1], ready for fusion", scored, optional=True)


if not fts5_available():
    CHECKS.append({"name": "Environment blocked", "passed": False, "detail": "Your Python's sqlite3 module was built without FTS5 (CREATE VIRTUAL TABLE … USING fts5 fails). Install a Python whose SQLite carries FTS5 (python.org builds and Homebrew do), then verify again."})
else:
    try:
        trial()
    except Exception as error:
        CHECKS.append({"name": "Load lexical index", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
