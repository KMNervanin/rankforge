"""Model-judge calibration checks for the Judge mission; run outside the learner workspace.

The scripted adapter below is a labeled test tool: it speaks the chat completions contract and
answers PASS/FAIL or A/B from rules Verify chooses (a hidden marker, a position bias, a length bias,
a score instead of a verdict), recording every request body. Expected rates are computed here from
the planted labels, never from the learner's code. The only live evaluation is the final measurement
of four labeled fixtures against the endpoint the learner configured in llm.json.
"""
import hashlib
import importlib.util
import json
import os
import random
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.request
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, HTTPServer

MISSION, WORKSPACE = sys.argv[1:3]
CHECKS = []
LIVE_TIMEOUT = 15
LIVE_BUDGET = 20
MODEL = "relay-judge"
TOLERANCE = Fraction(1, 10**9)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check(name, operation, optional=False):
    # An optional check is the hidden bonus of a mission: it can only add, it never fails the run.
    flag = {"optional": True} if optional else {}
    try:
        detail = operation()
        CHECKS.append({"name": name, "passed": True, "detail": detail or "Scripted adapter requests and the returned results verified.", **flag})
    except Exception as error:
        CHECKS.append({"name": name, "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500], **flag})


class EnvironmentBlocked(Exception):
    pass


class Adapter(socketserver.ThreadingMixIn, HTTPServer):
    """OpenAI-compatible loopback server; `answer(text, index)` decides the reply from the joined message text."""
    daemon_threads = True

    def __init__(self, answer):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.answer = answer
        self.requests = []
        self.lock = threading.Lock()

    def server_bind(self):
        # Loopback validation must not wait on VPN-dependent reverse DNS.
        socketserver.TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        pass

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server_port}/v1"


def message_text(body):
    return "\n".join(str(message.get("content") or "") for message in body.get("messages", []) if isinstance(message, dict))


def message_hashes(body):
    return {hashlib.sha256(str(message.get("content") or "").encode("utf-8")).hexdigest(): str(message.get("content") or "") for message in body.get("messages", []) if isinstance(message, dict)}


class AdapterHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        server: Adapter = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
            require(isinstance(body, dict) and isinstance(body.get("messages"), list) and body["messages"], "messages required")
            require(isinstance(body.get("model"), str) and body["model"], "model required")
        except Exception as error:
            self.reply(400, {"error": {"message": f"invalid request: {error}", "type": "invalid_request_error"}})
            return
        with server.lock:
            server.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            index = len(server.requests)
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        content = server.answer(message_text(body), index)
        prompt_tokens = 30 + 2 * len(body["messages"])
        self.reply(200, {
            "id": f"chatcmpl-adapter-{index}", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 1, "total_tokens": prompt_tokens + 1},
            "system_fingerprint": "fp_scripted_adapter",
        })


def serve(answer):
    server = Adapter(answer)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


RANDOM = random.Random()
RUN = f"{RANDOM.randrange(16**6):06x}"
MARKER = f"ref-{RANDOM.randrange(16**5):05x}"
VERSION = f"judge-v{RANDOM.randint(2, 9)}.{RANDOM.randint(0, 20)}"
CRITERION = {"id": f"cites-{RUN}", "name": "Answer cites a source that supports it",
             "instruction": f"The answer names a source and that source actually supports the claim (audit tag {RUN})."}
SCOPE = {"id": f"scope-{RUN}", "name": "Answer stays within the operator's request",
         "instruction": f"The answer addresses only what the operator asked and does not add unrequested actions (audit tag {RUN})."}
SOURCES = ["RB-17 §3: replace the relay air filter every 90 days.", "P-4: an operator may reserve stock only for their own outpost.",
           "RB-02: fuse orders are capped at twelve boxes per convoy.", "IR-311: generator two ran dry after the valve was left open."]
REQUESTS = ["How often is the north relay's air filter replaced?", "May I reserve diesel for outpost Delta?",
            "What is the fuse cap per convoy?", "Why did generator two stop overnight?"]


def item(index, *, marked, suffix=""):
    answer = f"Answer {index} ({RUN}): {'per ' + MARKER + ', ' if marked else ''}the runbook procedure applies{suffix}."
    return {"id": f"item-{RUN}-{index}", "request": REQUESTS[index % 4], "answer": answer, "source": SOURCES[index % 4]}


def marker_rule(text, index):
    return "PASS" if MARKER in text else "FAIL"


def prefer(wanted, other):
    def answer(text, index):
        require(wanted in text and other in text, "both answers must be in the pairwise request")
        return "A" if text.index(wanted) < text.index(other) else "B"
    return answer


def longer(first, second):
    long_text, short_text = (first, second) if len(first) >= len(second) else (second, first)
    return prefer(long_text, short_text)


def fraction(value):
    require(isinstance(value, (int, float, Fraction)) and not isinstance(value, bool), f"rates must be numbers, got {value!r}")
    return Fraction(str(value)) if isinstance(value, float) else Fraction(value)


def expected_rates(pairs):
    """pairs: (label, judged) booleans; the oracle's own Fraction arithmetic."""
    tp = sum(1 for label, judged in pairs if label and judged)
    fn = sum(1 for label, judged in pairs if label and not judged)
    tn = sum(1 for label, judged in pairs if not label and not judged)
    fp = sum(1 for label, judged in pairs if not label and judged)
    return {"tpr": Fraction(tp, tp + fn), "tnr": Fraction(tn, tn + fp), "agreement": Fraction(tp + tn, len(pairs)), "n_pos": tp + fn, "n_neg": tn + fp}


def same_rates(actual, wanted):
    for key in ("tpr", "tnr", "agreement"):
        require(key in actual, f"the calibration is missing {key!r}")
        require(abs(fraction(actual[key]) - wanted[key]) <= TOLERANCE, f"{key} is {actual[key]!r}, expected {wanted[key]} = {float(wanted[key])!r}")
    for key in ("n_pos", "n_neg"):
        require(type(actual.get(key)) is int and actual[key] == wanted[key], f"{key} is {actual.get(key)!r}, expected {wanted[key]}")


def trial():
    require(MISSION == "judge", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_judge", os.path.join(WORKSPACE, "judge.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load judge.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("judge_binary", "judge_pairwise", "length_bias_probe", "calibrate", "require_labels", "calibration_report"):
        require(callable(getattr(candidate, name, None)), f"judge.py must define {name}(...)")
    parse_error = getattr(candidate, "JudgeParseError", None)
    parse_errors = (parse_error,) if isinstance(parse_error, type) and issubclass(parse_error, BaseException) else ()
    unlabeled_error = getattr(candidate, "UnlabeledCriterionError", None)

    def pinned(result, request, *, version=VERSION):
        require(isinstance(result, dict), f"results are dicts, got {type(result).__name__}")
        require(result.get("judge_version") == version, f"judge_version must be the value passed ({version!r}), got {result.get('judge_version')!r}")
        require(result.get("model") == MODEL, f"model must be the model id called ({MODEL!r}), got {result.get('model')!r}")
        digest = result.get("prompt_hash")
        require(isinstance(digest, str) and len(digest) == 64 and all(char in "0123456789abcdef" for char in digest), f"prompt_hash must be a lowercase sha256 hex digest, got {digest!r}")
        hashes = message_hashes(request["body"])
        require(digest in hashes, "prompt_hash must be the sha256 of one message content sent in the request (the criterion prompt)")
        return hashes[digest]

    def binary(server, criterion, subject, *, version=VERSION, **options):
        before = len(server.requests)
        result = candidate.judge_binary(criterion, subject, base_url=server.base_url, model=MODEL, judge_version=version, **options)
        require(len(server.requests) - before == 1, f"judge_binary must send exactly one request, saw {len(server.requests) - before}")
        request = server.requests[-1]
        require(isinstance(result, dict) and type(result.get("verdict")) is bool, f"judge_binary returns a dict with a boolean verdict, got {result!r}"[:400])
        require(result.get("item_id") == subject["id"], f"the result carries item_id {subject['id']!r}, got {result.get('item_id')!r}")
        require(isinstance(result.get("raw"), str), "the result carries the raw judge text")
        return result, request

    def pairwise(server, criterion, a, b, *, version=VERSION):
        before = len(server.requests)
        result = candidate.judge_pairwise(criterion, a, b, base_url=server.base_url, model=MODEL, judge_version=version)
        sent = server.requests[before:]
        require(len(sent) == 2, f"judge_pairwise must call the judge twice (both orders), saw {len(sent)} request(s)")
        texts = [message_text(request["body"]) for request in sent]
        require(all(a["answer"] in text and b["answer"] in text for text in texts), "both answers must be in each pairwise request")
        orders = [(text.index(a["answer"]) < text.index(b["answer"])) for text in texts]
        require(orders[0] != orders[1], "the two pairwise requests must present the answers in opposite orders")
        require(isinstance(result, dict) and result.get("result") in ("win", "loss", "tie"), f"judge_pairwise returns result win, loss or tie, got {result!r}"[:400])
        return result, sent

    def binary_judge():
        server, thread = serve(marker_rule)
        try:
            marked, plain = item(0, marked=True), item(1, marked=False)
            result, request = binary(server, CRITERION, marked)
            require(result["verdict"] is True and result["raw"] == "PASS", f"PASS must give verdict True with raw 'PASS', got {result!r}"[:300])
            body = request["body"]
            require(body.get("model") == MODEL, f"the request must name the model id {MODEL!r}, got {body.get('model')!r}")
            require(type(body.get("max_tokens")) is int and 1 <= body["max_tokens"] <= 64, f"max_tokens must be a small integer, got {body.get('max_tokens')!r}")
            text = message_text(body)
            for label, needle in (("criterion instruction", CRITERION["instruction"]), ("request", marked["request"]), ("answer", marked["answer"]), ("source", marked["source"])):
                require(needle in text, f"the judge request must contain the {label} verbatim")
            require("PASS" in text and "FAIL" in text, "the prompt must ask for the words PASS or FAIL")
            result, _ = binary(server, CRITERION, plain)
            require(result["verdict"] is False and result["raw"] == "FAIL", f"FAIL must give verdict False, got {result!r}"[:300])
            return "One request per item carrying the criterion prompt, request, source and answer; PASS and FAIL parsed to booleans."
        finally:
            stop(server, thread)
    check("Binary judge: one request per item carrying the criterion prompt and the item, verdict PASS or FAIL", binary_judge)

    def strict_parse():
        require(isinstance(parse_error, type) and issubclass(parse_error, Exception), "judge.py must define the JudgeParseError exception class")
        answers = [f"{RANDOM.randint(6, 9)}/10", f"Score: {RANDOM.randint(5, 9)} out of 10", "Mostly PASS", "", "pass or fail"]
        state = {"index": 0}
        server, thread = serve(lambda text, index: answers[min(state["index"], len(answers) - 1)])
        try:
            subject = item(2, marked=True)
            for position, answer in enumerate(answers):
                state["index"] = position
                try:
                    result = candidate.judge_binary(CRITERION, subject, base_url=server.base_url, model=MODEL, judge_version=VERSION)
                except parse_error:
                    continue
                raise AssertionError(f"the judge answered {answer!r} and judge_binary returned {result!r} instead of raising JudgeParseError"[:400])
            require(len(server.requests) == len(answers), "each judgment sends one request before parsing")
        finally:
            stop(server, thread)
        server, thread = serve(lambda text, index: " Pass.\n")
        try:
            result, _ = binary(server, CRITERION, item(3, marked=False))
            require(result["verdict"] is True, "'Pass.' with surrounding whitespace and a trailing period is the word PASS")
        finally:
            stop(server, thread)
        a, b = item(4, marked=True), item(5, marked=False)
        b["request"], b["source"] = a["request"], a["source"]
        server, thread = serve(lambda text, index: RANDOM.choice(["C", "Answer A is better", "both", "A or B"]))
        try:
            try:
                result = candidate.judge_pairwise(CRITERION, a, b, base_url=server.base_url, model=MODEL, judge_version=VERSION)
            except parse_error:
                pass
            else:
                raise AssertionError(f"a pairwise answer that is not A, B or TIE must raise JudgeParseError, got {result!r}"[:400])
            return "Scores, prose and empty answers raised JudgeParseError for the binary judge, an unknown letter for the pairwise one; a bare verdict with punctuation still parsed."
        finally:
            stop(server, thread)
    check("A score or any text other than PASS or FAIL is a parse failure, never a verdict", strict_parse)

    def plant(count, *, positives=None):
        items, labels, pairs = [], [], []
        while True:
            marked = [RANDOM.random() < 0.55 for _ in range(count)]
            truth = [flag if RANDOM.random() < 0.75 else not flag for flag in marked] if positives is None else positives
            if {True, False} <= set(truth) and {True, False} <= set(marked):
                break
        for index, (flag, label) in enumerate(zip(marked, truth)):
            subject = item(index, marked=flag)
            subject["id"] = f"item-{RUN}-{index}-{RANDOM.randrange(1000):03d}"
            items.append(subject)
            labels.append({"item_id": subject["id"], "label": label})
            pairs.append((label, flag))
        return items, labels, pairs

    def calibration():
        items, labels, pairs = plant(10)
        wanted = expected_rates(pairs)
        server, thread = serve(marker_rule)
        try:
            verdicts = [binary(server, CRITERION, subject)[0] for subject in items]
            rates = candidate.calibrate(verdicts, labels)
            require(isinstance(rates, dict), "calibrate returns a dict")
            same_rates(rates, wanted)
            try:
                candidate.calibrate(verdicts[1:], labels)
            except ValueError:
                pass
            else:
                raise AssertionError("calibrate must raise ValueError when a labeled item has no verdict (ids must align)")
            try:
                candidate.calibrate(verdicts + [dict(verdicts[0])], labels)
            except ValueError:
                pass
            else:
                raise AssertionError("calibrate must raise ValueError when an item id has two verdicts")
        finally:
            stop(server, thread)
        skewed_items, skewed_labels, _ = plant(10, positives=[True] * 9 + [False])
        server, thread = serve(lambda text, index: "PASS")
        try:
            verdicts = [binary(server, CRITERION, subject)[0] for subject in skewed_items]
            rates = candidate.calibrate(verdicts, skewed_labels)
            same_rates(rates, {"tpr": Fraction(1), "tnr": Fraction(0), "agreement": Fraction(9, 10), "n_pos": 9, "n_neg": 1})
        finally:
            stop(server, thread)
        return f"TPR {wanted['tpr']}, TNR {wanted['tnr']}, agreement {wanted['agreement']} on {len(items)} fresh items; an always-PASS judge scored agreement 9/10 with TNR 0 on a 9:1 set."
    check("TPR, TNR and agreement against human labels match hand-computed values, including under class imbalance", calibration)

    def report():
        items, labels, pairs = plant(8)
        wanted = expected_rates(pairs)
        store = {CRITERION["id"]: labels, SCOPE["id"]: []}
        server, thread = serve(marker_rule)
        try:
            result = candidate.calibration_report(CRITERION, items, store, base_url=server.base_url, model=MODEL, judge_version=VERSION)
            require(isinstance(result, dict), "calibration_report returns a dict")
            for key in ("tpr", "tnr", "agreement", "n_pos", "n_neg"):
                require(key in result, f"the report must carry {key!r}; an averaged score with no agreement data is not a calibration")
            same_rates(result, wanted)
            require(len(server.requests) == len(items), f"the report judges each labeled item once ({len(items)} requests), saw {len(server.requests)}")
            require(isinstance(result.get("verdicts"), list) and len(result["verdicts"]) == len(items), "the report carries one verdict per labeled item")
            require({verdict.get("item_id") for verdict in result["verdicts"]} == {subject["id"] for subject in items}, "the report's verdicts carry the item ids")
            pinned(result, server.requests[-1])
            return f"Report carried TPR {wanted['tpr']}, TNR {wanted['tnr']}, agreement {wanted['agreement']}, {wanted['n_pos']} positives and {wanted['n_neg']} negatives with the judge pins."
        finally:
            stop(server, thread)
    check("The calibration report carries rates and class counts; an averaged 1-10 score without agreement data is rejected", report)

    def swap():
        a = item(4, marked=True)
        b = item(5, marked=False, suffix=f" ({RANDOM.randrange(1000):03d})")
        b["request"], b["source"] = a["request"], a["source"]
        server, thread = serve(prefer(a["answer"], b["answer"]))
        try:
            result, _ = pairwise(server, CRITERION, a, b)
            require(result["result"] == "win", f"a judge that prefers a's content in both orders means a wins, got {result['result']!r}")
            result, _ = pairwise(server, CRITERION, b, a)
            require(result["result"] == "loss", f"the same judge with b first means b loses, got {result['result']!r}")
        finally:
            stop(server, thread)
        server, thread = serve(lambda text, index: "TIE")
        try:
            result, _ = pairwise(server, CRITERION, a, b)
            require(result["result"] == "tie", f"TIE in both orders is a tie, got {result['result']!r}")
            return "Two requests with opposite orders per judgment; consistent preference counted as win or loss, TIE as tie."
        finally:
            stop(server, thread)
    check("Pairwise judgment calls the judge twice with swapped order and counts a win only when both orders agree", swap)

    def position_bias():
        a = item(6, marked=True)
        b = item(7, marked=False)
        b["request"], b["source"] = a["request"], a["source"]
        for fixed in ("A", "B"):
            server, thread = serve(lambda text, index, fixed=fixed: fixed)
            try:
                result, _ = pairwise(server, CRITERION, a, b)
                require(result["result"] == "tie", f"a judge that always answers {fixed} prefers a different answer in each order; that is a tie, got {result['result']!r}")
            finally:
                stop(server, thread)
        return "An always-A and an always-B judge both produced a tie under the swap rule."
    check("A position-biased judge yields a tie under the swap rule", position_bias)

    def length_bias():
        short_good = item(8, marked=True)
        padding = " ".join(["Additionally, as noted above, the procedure applies as described."] * RANDOM.randint(4, 7))
        long_padded = item(9, marked=False, suffix=" " + padding)
        long_padded["request"], long_padded["source"] = short_good["request"], short_good["source"]
        outcomes = {}
        for name, rule in (("length-biased", longer(short_good["answer"], long_padded["answer"])), ("content-based", prefer(short_good["answer"], long_padded["answer"]))):
            server, thread = serve(rule)
            try:
                result = candidate.length_bias_probe(CRITERION, short_good, long_padded, base_url=server.base_url, model=MODEL, judge_version=VERSION)
                require(isinstance(result, dict) and type(result.get("padded_won")) is bool, f"length_bias_probe returns a dict with a boolean padded_won, got {result!r}"[:300])
                require(len(server.requests) == 2, f"the probe is a pairwise judgment: two requests with swapped order, saw {len(server.requests)}")
                texts = [message_text(request["body"]) for request in server.requests]
                require(all(short_good["answer"] in text and long_padded["answer"] in text for text in texts), "both answers must be in each probe request")
                require((texts[0].index(short_good["answer"]) < texts[0].index(long_padded["answer"])) != (texts[1].index(short_good["answer"]) < texts[1].index(long_padded["answer"])), "the probe must swap the order between its two requests")
                outcomes[name] = result["padded_won"]
            finally:
                stop(server, thread)
        require(outcomes["length-biased"] is True, "a judge that always prefers the longer answer must be reported as padded_won true")
        require(outcomes["content-based"] is False, "a judge that prefers the short, supported answer must be reported as padded_won false")
        return "padded_won true under a length-biased judge, false under a content-based one; both probes swapped the order."
    check("The length-bias probe runs through the swap rule and reports whether the padded answer won", length_bias)

    def pins():
        a, b = item(4, marked=True), item(5, marked=False)
        b["request"], b["source"] = a["request"], a["source"]
        pair_rule = prefer(a["answer"], b["answer"])
        server, thread = serve(lambda text, index: pair_rule(text, index) if a["answer"] in text and b["answer"] in text else marker_rule(text, index))
        try:
            other = f"{VERSION}-candidate"
            prompts = {}
            for criterion in (CRITERION, SCOPE):
                hashes = set()
                for index in (0, 1):
                    result, request = binary(server, criterion, item(index, marked=bool(index)))
                    prompts[criterion["id"]] = pinned(result, request)
                    hashes.add(result["prompt_hash"])
                require(len(hashes) == 1, "one criterion has one prompt, so every item judged under it carries the same prompt_hash")
            require(prompts[CRITERION["id"]] != prompts[SCOPE["id"]], "two criteria are two prompts: their prompt_hash values must differ")
            require(CRITERION["instruction"] in prompts[CRITERION["id"]], "the hashed prompt is the criterion prompt: it contains the criterion instruction")
            result, request = binary(server, CRITERION, item(0, marked=True), version=other)
            pinned(result, request, version=other)
            result, sent = pairwise(server, CRITERION, a, b)
            pinned(result, sent[0])
            probe = candidate.length_bias_probe(CRITERION, a, b, base_url=server.base_url, model=MODEL, judge_version=VERSION)
            pinned(probe, server.requests[-1])
            return f"Binary, pairwise, probe and report results all carried judge_version {VERSION!r}, model {MODEL!r} and the sha256 of the criterion prompt sent."
        finally:
            stop(server, thread)
    check("Every result pins judge_version, model id and the prompt hash of the criterion prompt sent", pins)

    def transfer():
        require(isinstance(unlabeled_error, type) and issubclass(unlabeled_error, Exception), "judge.py must define the UnlabeledCriterionError exception class")
        items, labels, _ = plant(6)
        fresh = {"id": f"tone-{RUN}", "name": "Answer keeps a neutral tone", "instruction": f"The answer states facts without blame or speculation (audit tag {RUN})."}
        only_positive = [dict(label, label=True) for label in labels]
        store = {CRITERION["id"]: labels, SCOPE["id"]: only_positive}
        for criterion, reason in ((fresh, "no labels at all"), (SCOPE, "labels of one class only")):
            try:
                candidate.require_labels(criterion, store)
            except unlabeled_error:
                pass
            else:
                raise AssertionError(f"require_labels must raise UnlabeledCriterionError for a criterion with {reason}")
        returned = candidate.require_labels(CRITERION, store)
        require(isinstance(returned, list) and len(returned) == len(labels) and {label["item_id"] for label in returned} == {label["item_id"] for label in labels}, "require_labels returns the criterion's labels when both classes are present")
        server, thread = serve(marker_rule)
        try:
            try:
                candidate.calibration_report(fresh, items, store, base_url=server.base_url, model=MODEL, judge_version=VERSION)
            except unlabeled_error:
                pass
            else:
                raise AssertionError("calibration_report on an unlabeled criterion must raise UnlabeledCriterionError")
            require(len(server.requests) == 0, "an unlabeled criterion is refused before any judge request is sent")
            return "A new criterion without labels and one with labels of a single class were refused with no request; the labeled criterion returned its labels."
        finally:
            stop(server, thread)
    check("Transfer: a criterion without human labels of both classes is refused before any request", transfer)

    def consistency():
        probe = getattr(candidate, "consistency_probe", None)
        require(callable(probe), "judge.py may define consistency_probe(criterion, item, *, base_url, model, judge_version, k=5, ...)")
        k = RANDOM.randint(5, 7)
        while True:
            pattern = [RANDOM.random() < 0.5 for _ in range(k)]
            if {True, False} <= set(pattern):
                break
        server, thread = serve(lambda text, index: "PASS" if pattern[(index - 1) % k] else "FAIL")
        try:
            result = probe(CRITERION, item(1, marked=True), base_url=server.base_url, model=MODEL, judge_version=VERSION, k=k)
            require(isinstance(result, dict), "consistency_probe returns a dict")
            require(len(server.requests) == k, f"the probe judges the item k={k} times, saw {len(server.requests)} requests")
            require(result.get("verdicts") == pattern, f"verdicts must list the k parsed verdicts in order, got {result.get('verdicts')!r}")
            wanted = Fraction(k - max(pattern.count(True), pattern.count(False)), k)
            require(abs(fraction(result.get("flip_rate")) - wanted) <= TOLERANCE, f"flip_rate is the minority share {wanted}, got {result.get('flip_rate')!r}")
            pinned(result, server.requests[-1])
            return f"k={k} repeated judgments, flip rate {wanted} reported with the judge pins."
        finally:
            stop(server, thread)
    check("bonus: a self-consistency probe reports the flip rate over k repeated judgments", consistency, optional=True)

    LIVE_FIXTURES = [
        ({"id": "live-1", "request": REQUESTS[0], "answer": "Every 90 days, per runbook RB-17 section 3.", "source": SOURCES[0]}, True),
        ({"id": "live-2", "request": REQUESTS[1], "answer": "No. Policy P-4 limits reservations to the operator's own outpost.", "source": SOURCES[1]}, True),
        ({"id": "live-3", "request": REQUESTS[2], "answer": "Forty boxes per convoy, as stated in RB-02.", "source": SOURCES[2]}, False),
        ({"id": "live-4", "request": REQUESTS[3], "answer": "Probably a fuel delivery problem; the convoy was late.", "source": SOURCES[3]}, False),
    ]
    LIVE_CRITERION = {"id": "cites-source", "name": "Answer cites a source that supports it",
                      "instruction": "The answer names the source it relies on, and that source actually supports the claim the answer makes."}

    def live():
        config_path = os.path.join(WORKSPACE, "llm.json")
        try:
            with open(config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
        except Exception as error:
            raise EnvironmentBlocked(f"llm.json could not be read ({type(error).__name__}: {error}). It holds base_url and model only; keys stay in the environment.")
        base_url, model = str(config.get("base_url") or ""), str(config.get("model") or "")
        if not base_url or not model:
            raise EnvironmentBlocked("Set base_url and model in llm.json to your own endpoint (for Ollama: http://127.0.0.1:11434/v1 and a name from `ollama list`), then verify again.")
        ping = json.dumps({"model": model, "messages": [{"role": "user", "content": "Reply with the single word OK."}], "max_tokens": 4, "temperature": 0}).encode("utf-8")
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=ping, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=LIVE_TIMEOUT) as response:
                raw = response.read()
            try:
                json.loads(raw.decode("utf-8"))
            except ValueError:
                raise EnvironmentBlocked(f"{base_url} answered the warm-up request with something that is not JSON: {raw[:120]!r}. Point llm.json at an OpenAI-compatible /v1 endpoint.")
        except EnvironmentBlocked:
            raise
        except urllib.error.HTTPError as error:
            raise EnvironmentBlocked(f"{base_url} answered HTTP {error.code} for model {model!r}: {error.read(300).decode('utf-8', 'replace')}")
        except Exception as error:
            raise EnvironmentBlocked(f"{base_url} did not answer within {LIVE_TIMEOUT} s ({type(error).__name__}: {error}). Start or warm up the model with demo.py, then verify again.")
        version = str(config.get("judge_version") or "live-judge")
        started = time.perf_counter()
        verdicts, failures, hashes = [], [], set()
        for subject, label in LIVE_FIXTURES:
            try:
                result = candidate.judge_binary(LIVE_CRITERION, subject, base_url=base_url, model=model, judge_version=version, max_tokens=int(config.get("max_tokens") or 8))
            except parse_errors as error:
                failures.append(str(error)[:80])
                continue
            require(isinstance(result, dict) and type(result.get("verdict")) is bool, f"judge_binary returns a boolean verdict, got {result!r}"[:300])
            require(result.get("judge_version") == version and result.get("model") == model, "the live results must pin the judge version and the model id from llm.json")
            require(isinstance(result.get("prompt_hash"), str) and len(result["prompt_hash"]) == 64, "the live results must carry the prompt hash")
            hashes.add(result["prompt_hash"])
            verdicts.append((label, result["verdict"]))
        require(len(hashes) <= 1, "one criterion, one prompt hash across the live run")
        seconds = time.perf_counter() - started
        tp = sum(1 for label, judged in verdicts if label and judged)
        tn = sum(1 for label, judged in verdicts if not label and not judged)
        n_pos = sum(1 for label, _ in verdicts if label)
        n_neg = len(verdicts) - n_pos
        agreement = f"{tp + tn}/{len(verdicts)}" if verdicts else "n/a"
        tpr = f"{tp}/{n_pos}" if n_pos else "n/a"
        tnr = f"{tn}/{n_neg}" if n_neg else "n/a"
        parse_note = f"; parse failures: {failures}" if failures else ""
        return (f"Live: {model} at {base_url}; judge {version!r}, prompt {next(iter(hashes))[:12] if hashes else 'n/a'}; 4 judgments in {seconds:.1f} s: "
                f"{len(verdicts)}/4 parsed, agreement {agreement}, TPR {tpr}, TNR {tnr}{parse_note}. These are measurements of one run against four labels, not a verdict on the model.")

    def live_bounded():
        # The learner's HTTP timeout is theirs; Verify's own budget for the whole live section is LIVE_BUDGET seconds.
        outcome = {}

        def worker():
            try:
                outcome["detail"] = live()
            except BaseException as error:  # noqa: BLE001 - carried to the main thread
                outcome["error"] = error
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=LIVE_BUDGET)
        if thread.is_alive():
            raise EnvironmentBlocked(f"The live measurement did not finish within {LIVE_BUDGET} s; the endpoint in llm.json is too slow for this check. Warm the model up with demo.py or use a smaller one, then verify again.")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["detail"]

    try:
        CHECKS.append({"name": "Live run: binary judge agreement with four labeled fixtures on the configured endpoint", "passed": True, "detail": live_bounded()})
    except EnvironmentBlocked as blocked:
        CHECKS.append({"name": "Environment blocked", "passed": False, "detail": str(blocked)[:1500]})
    except Exception as error:
        CHECKS.append({"name": "Live run: binary judge agreement with four labeled fixtures on the configured endpoint", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load judge", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
