"""Cited answers and abstention checks for the Citations mission; run outside the learner workspace.

The scripted adapter below is a labeled test tool: it speaks the chat completions contract and
answers with chosen outputs in a chosen order, recording every request body. The scripted judge
decides each claim from a hidden rule so the expected faithfulness is known in advance. The only
live evaluation is the final measurement against the endpoint the learner configured in llm.json.
"""
import importlib.util
import json
import os
import random
import re
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
PHRASE = "the archive does not answer this"
MARKER = re.compile(r"\s*\[[^\]]*\]")


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
    """OpenAI-compatible loopback server that answers from a script; the last step repeats forever."""
    daemon_threads = True

    def __init__(self, script):
        super().__init__(("127.0.0.1", 0), AdapterHandler)
        self.script = list(script)
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
            content = server.script[min(len(server.requests), len(server.script)) - 1]
            index = len(server.requests)
        if not self.path.endswith("/chat/completions"):
            self.reply(404, {"error": {"message": "unknown route", "type": "invalid_request_error"}})
            return
        prompt_tokens = 60 + 3 * len(body["messages"])
        produced = len(str(content).split()) + 1
        self.reply(200, {
            "id": f"chatcmpl-adapter-{index}", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": produced, "total_tokens": prompt_tokens + produced},
            "system_fingerprint": "fp_scripted_adapter",
        })


def serve(script):
    server = Adapter(script)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    return server, thread


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def normalize(text):
    return " ".join(str(text).split())


def claims_of(body):
    flat = normalize(MARKER.sub("", body))
    return [piece.strip() for piece in re.split(r"(?<=[.!?])\s+", flat) if piece.strip()]


def message_text(request):
    return normalize(" ".join(str(message.get("content") or "") for message in request["body"]["messages"]))


RANDOM = random.Random()
IDS = [f"p{number}" for number in RANDOM.sample(range(10, 99), 8)]
A, B, C, D, GHOST, V1, V2, OTHER = IDS
WAIT = RANDOM.choice(range(45, 125, 5))
LOCKER = RANDOM.randint(2, 9)
MINUTES = RANDOM.randint(25, 55)
TOKEN = RANDOM.choice(["quartz", "zinc", "cobalt", "basalt", "argon"]) + str(RANDOM.randint(10, 99))
PASSAGES = [
    {"id": A, "doc": "runbook-relay", "version": 3, "text": f"Relay 4 restart procedure: switch the relay off, wait {WAIT} seconds, then\n   switch it on again. If the status lamp stays red after the second attempt, open an incident report."},
    {"id": B, "doc": "runbook-stock", "version": 1, "text": f"Spare fuses for the relays are kept in locker {LOCKER} of the north depot. The locker key is signed out from the operator on duty."},
    {"id": C, "doc": "incident-2231", "version": 1, "text": f"Incident 2231: generator two ran dry at 03:40 because the diesel reserve had not been refilled after the convoy. Refilling took {MINUTES} minutes."},
    {"id": D, "doc": "runbook-water", "version": 1, "text": "Water filters are replaced every ninety days or after a turbidity alarm, whichever comes first."},
]
QUESTION = "How long should the operator wait after switching relay 4 off, and where are the spare fuses?"
QUOTE_A = f"wait {WAIT} seconds, then switch it on again"
QUOTE_B = f"kept in locker {LOCKER} of the north depot"
BODY = f"Switch relay 4 off and wait {WAIT} seconds before switching it on again [{A}]. Spare fuses are in locker {LOCKER} of the north depot [{B}]."
GOOD = f"{BODY}\nSources:\n[{A}] \"{QUOTE_A}\"\n[{B}] \"{QUOTE_B}\""
GHOST_ID = f"{BODY}\nSources:\n[{A}] \"{QUOTE_A}\"\n[{GHOST}] \"{QUOTE_B}\""
PARAPHRASE = f"wait about {WAIT} seconds and restart the relay"
GHOST_QUOTE = f"{BODY}\nSources:\n[{A}] \"{PARAPHRASE}\"\n[{B}] \"{QUOTE_B}\""
FABRICATED_BODY = f"{BODY} The relay also accepts {TOKEN} batteries [{A}]."
FABRICATED = f"{FABRICATED_BODY}\nSources:\n[{A}] \"{QUOTE_A}\"\n[{B}] \"{QUOTE_B}\""
REFUSAL = f"I am sorry, but {PHRASE} question."
NO_SOURCES = f"Switch relay 4 off and wait {WAIT} seconds before switching it on again."
WAIT_V1, WAIT_V2 = RANDOM.sample([20, 30, 45, 60, 90, 120], 2)
VERSIONS = [
    {"id": V2, "doc": "runbook-relay", "version": 2, "text": f"Relay 4 restart procedure: switch the relay off, wait {WAIT_V2} seconds, then switch it on again."},
    {"id": OTHER, "doc": "runbook-stock", "version": 1, "text": f"Spare fuses for the relays are kept in locker {LOCKER} of the north depot."},
    {"id": V1, "doc": "runbook-relay", "version": 1, "text": f"Relay 4 restart procedure: switch the relay off, wait {WAIT_V1} seconds, then switch it on again."},
]
CONFLICT_QUESTION = "How long should the operator wait after switching relay 4 off?"
ONLY_V2 = f"Wait {WAIT_V2} seconds [{V2}].\nSources:\n[{V2}] \"wait {WAIT_V2} seconds\""
ONLY_V1 = f"Wait {WAIT_V1} seconds [{V1}].\nSources:\n[{V1}] \"wait {WAIT_V1} seconds\""
BOTH = f"Version 1 says {WAIT_V1} seconds [{V1}] but version 2 says {WAIT_V2} seconds [{V2}]; the two versions disagree.\nSources:\n[{V1}] \"wait {WAIT_V1} seconds\"\n[{V2}] \"wait {WAIT_V2} seconds\""

LIVE_PASSAGES = [
    {"id": "p1", "doc": "runbook-relay", "version": 3, "text": "Relay 4 restart procedure: switch the relay off, wait 90 seconds, then switch it on again. If the status lamp stays red after the second attempt, open an incident report."},
    {"id": "p2", "doc": "runbook-stock", "version": 1, "text": "Spare fuses for the relays are kept in locker 7 of the north depot. The locker key is signed out from the operator on duty."},
    {"id": "p3", "doc": "incident-2231", "version": 1, "text": "Incident 2231: generator two ran dry at 03:40 because the diesel reserve had not been refilled after the convoy. Refilling took forty minutes."},
    {"id": "p4", "doc": "runbook-water", "version": 1, "text": "Water filters are replaced every ninety days or after a turbidity alarm, whichever comes first."},
]
LIVE_QUESTIONS = [("answerable", "How long should the operator wait after switching relay 4 off?"), ("unanswerable", "What is the price of diesel at the south depot?")]


def citation_pairs(result):
    return [(citation.get("passage_id"), citation.get("quote")) for citation in result["citations"]]


def valid_citations(result, passages):
    lookup = {passage["id"]: normalize(passage["text"]) for passage in passages}
    return [citation for citation in result["citations"] if citation.get("passage_id") in lookup and normalize(citation.get("quote") or "") and normalize(citation["quote"]) in lookup[citation["passage_id"]]]


def trial():
    require(MISSION == "citations", "Unknown mission")
    sys.path.insert(0, WORKSPACE)
    spec = importlib.util.spec_from_file_location("candidate_citations", os.path.join(WORKSPACE, "answer.py"))
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load answer.py")
    candidate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = candidate
    spec.loader.exec_module(candidate)
    for name in ("answer", "faithfulness", "reconcile"):
        require(callable(getattr(candidate, name, None)), f"answer.py must define {name}(...)")

    def ask(server, question, passages, **options):
        options.setdefault("max_tokens", 300)
        result = candidate.answer(question, passages, base_url=server.base_url, model="archive-small", **options)
        require(isinstance(result, dict), "answer must return a dict")
        missing = {"status", "text", "citations", "claims", "attempts"} - set(result)
        require(not missing, f"The result is missing keys: {sorted(missing)}")
        require(result["status"] in ("answered", "abstained"), f"status must be answered or abstained, got {result['status']!r}")
        require(isinstance(result["citations"], list) and isinstance(result["claims"], list), "citations and claims must be lists")
        require(type(result["attempts"]) is int and result["attempts"] == len(server.requests), f"attempts {result['attempts']!r} must equal the {len(server.requests)} requests actually sent")
        if result["status"] == "abstained":
            require(str(result["text"]).strip().casefold().startswith(PHRASE), f"An abstention's text must start with the published phrase {PHRASE!r}, got {result['text']!r}")
            require(result["citations"] == [] and result["claims"] == [], "An abstention never carries citations or claims")
            require(isinstance(result.get("reason"), str) and result["reason"].strip(), "An abstention carries a non-empty reason")
        else:
            require(result["citations"], "An answered result carries at least one citation")
            for citation in result["citations"]:
                require(isinstance(citation, dict) and isinstance(citation.get("passage_id"), str) and isinstance(citation.get("quote"), str), f"Each citation is a dict with passage_id and quote, got {citation!r}")
            flat = normalize(MARKER.sub("", str(result["text"])))
            for claim in result["claims"]:
                require(claim in flat, f"Every claim must appear in text once markers are removed; missing {claim!r}")
        return result

    def empty():
        server, thread = serve([GOOD])
        try:
            result = ask(server, QUESTION, [])
            require(result["status"] == "abstained", f"An empty passage set must abstain, got {result['status']!r}")
            require(len(server.requests) == 0, f"An empty passage set sends no request, saw {len(server.requests)}")
            return "No passages: abstained with the published phrase and no request."
        finally:
            stop(server, thread)
    check("An empty passage set abstains with the published phrase and sends no request", empty)

    def request_contents():
        server, thread = serve([GOOD])
        try:
            ask(server, QUESTION, PASSAGES)
            require(len(server.requests) == 1, f"A valid answer takes one request, saw {len(server.requests)}")
            body = server.requests[0]["body"]
            require(type(body.get("max_tokens")) is int and body["max_tokens"] == 300, f"max_tokens must be sent as the integer given (300), got {body.get('max_tokens')!r}")
            require(body.get("stream") in (None, False), "Streaming is out of scope; do not send stream: true")
            text = message_text(server.requests[0])
            require(QUESTION in text, "The question must be sent verbatim in the messages")
            for passage in PASSAGES:
                require(f"[{passage['id']}]" in text, f"The passage id [{passage['id']}] must appear in the messages")
                require(normalize(passage["text"]) in text, f"The text of passage {passage['id']} must be sent verbatim")
            require(PHRASE in text.casefold(), f"The messages must tell the model the abstention phrase {PHRASE!r}")
            require("sources:" in text.casefold(), "The messages must name the Sources: block the model is to write")
            return "One request with the question, every passage with its id, the abstention phrase and the Sources: format."
        finally:
            stop(server, thread)
    check("The request carries the question, every passage with its id, and the abstention phrase", request_contents)

    def cited():
        server, thread = serve([GOOD])
        try:
            result = ask(server, QUESTION, PASSAGES)
            require(result["status"] == "answered", f"A correctly cited answer is answered, got {result['status']!r} ({result.get('reason')!r})")
            require(citation_pairs(result) == [(A, QUOTE_A), (B, QUOTE_B)], f"citations must be the validated pairs in reply order with normalized quotes, got {citation_pairs(result)!r}")
            require(result["claims"] == claims_of(BODY), f"claims must be the sentences of the answer body with markers removed: expected {claims_of(BODY)!r}, got {result['claims']!r}")
            require(result["attempts"] == 1, "A valid first answer makes exactly one request")
            require(result.get("reason") in (None, ""), "An answered result has no reason")
            return f"Two citations accepted, one across a line break in the passage; {len(result['claims'])} claims extracted."
        finally:
            stop(server, thread)
    check("Scripted adapter: a cited answer is validated in code and returned with its claims", cited)

    def ghost_id():
        server, thread = serve([GHOST_ID, GOOD])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=1)
            require(result["status"] == "answered" and result["attempts"] == 2, f"A fabricated id is rejected and the corrected answer accepted on the retry: got {result['status']!r} after {result['attempts']} requests")
            require(citation_pairs(result) == [(A, QUOTE_A), (B, QUOTE_B)], "The accepted citations are the retry's")
        finally:
            stop(server, thread)
        server, thread = serve([GHOST_ID])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=1)
            require(result["status"] == "abstained", f"Two answers citing an id outside the retrieved set must end abstained, got {result['status']!r}")
            require(result["attempts"] == 2, f"max_retries=1 means two requests, saw {result['attempts']}")
            require(GHOST in result["reason"], f"The reason names the fabricated id {GHOST}, got {result['reason']!r}")
            return f"[{GHOST}] was never retrieved: rejected in code, retried once, then abstained with the id in the reason."
        finally:
            stop(server, thread)
    check("A citation to a passage id outside the retrieved set is rejected in code", ghost_id)

    def ghost_quote():
        server, thread = serve([GHOST_QUOTE])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=1)
            require(result["status"] == "abstained", f"A quote that is not in its passage must be rejected, got {result['status']!r} with {citation_pairs(result)!r}")
            require(result["attempts"] == 2, f"max_retries=1 means two requests, saw {result['attempts']}")
            require(A in result["reason"], f"The reason names the passage {A} whose quote was not verbatim, got {result['reason']!r}")
        finally:
            stop(server, thread)
        server, thread = serve([GHOST_QUOTE, GOOD])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=1)
            require(result["status"] == "answered" and result["attempts"] == 2, "The corrected quote is accepted on the retry")
            return f"\"{PARAPHRASE}\" is not a span of [{A}]: rejected in code, not by a judge."
        finally:
            stop(server, thread)
    check("A quote that is not a verbatim span of its passage is rejected in code", ghost_quote)

    def retry():
        server, thread = serve([GHOST_ID])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=2)
            require(result["status"] == "abstained" and result["attempts"] == 3, f"max_retries=2 means three requests then abstention, got {result['status']!r} after {result['attempts']}")
            for request in server.requests[1:]:
                text = message_text(request)
                require(GHOST in text and QUOTE_B in text, "Each retry request quotes the rejected citation: its id and its quote")
                require(QUESTION in text, "Each retry request carries the question")
        finally:
            stop(server, thread)
        server, thread = serve([GHOST_ID])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=0)
            require(result["status"] == "abstained" and result["attempts"] == 1, f"max_retries=0 means a single request, saw {result['attempts']}")
            return "Three requests for max_retries=2, one for max_retries=0; every retry names the rejected citation and the question."
        finally:
            stop(server, thread)
    check("The retry request names the rejected citation and the retry bound holds", retry)

    def refusal():
        server, thread = serve([REFUSAL])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=1)
            require(result["status"] == "abstained", f"A reply containing the phrase is a refusal and must abstain, got {result['status']!r}")
            require(result["attempts"] == 1, f"A refusal is final: no retry, but {result['attempts']} requests were sent")
        finally:
            stop(server, thread)
        server, thread = serve([NO_SOURCES])
        try:
            result = ask(server, QUESTION, PASSAGES, max_retries=1)
            require(result["status"] == "abstained", f"An answer with no citation at all is not an answer; expected abstained, got {result['status']!r}")
            require(result["attempts"] == 2, f"An answer without sources is rejected and retried once before abstaining; saw {result['attempts']} requests")
            return "A refusal abstains at once; an uncited answer is retried once, then abstains. Neither carries citations."
        finally:
            stop(server, thread)
    check("A refusal abstains with the published phrase and never carries citations", refusal)

    def faithfulness():
        calls = []

        def judge(claim, passages):
            calls.append((claim, passages))
            return TOKEN not in str(claim)
        server, thread = serve([FABRICATED])
        try:
            result = ask(server, QUESTION, PASSAGES)
            require(result["status"] == "answered", "An answer whose citations are verbatim is answered even when a claim is fabricated; the judge, not the citation check, catches that")
            expected_claims = claims_of(FABRICATED_BODY)
            require(result["claims"] == expected_claims, f"claims expected {expected_claims!r}, got {result['claims']!r}")
            report = candidate.faithfulness(result, PASSAGES, judge)
            require(isinstance(report, dict) and {"supported", "total", "score", "verdicts"} <= set(report), "faithfulness returns supported, total, score and verdicts")
            require([call[0] for call in calls] == expected_claims, f"The judge is called once per claim, in order, with the claim text; saw {[call[0] for call in calls]!r}")
            require(all(call[1] == PASSAGES for call in calls), "The judge receives the retrieved passages")
            require(report["supported"] == 2 and report["total"] == 3, f"supported/total expected 2/3 from the judge's verdicts, got {report['supported']}/{report['total']}")
            require(abs(Fraction(str(report["score"])) - Fraction(2, 3)) <= Fraction(1, 10**9), f"score must be supported / total = {float(Fraction(2, 3))!r}, got {report['score']!r}")
            require([verdict.get("supported") for verdict in report["verdicts"]] == [True, True, False], f"verdicts carry the judge's decision per claim in order, got {report['verdicts']!r}")
            require([verdict.get("claim") for verdict in report["verdicts"]] == expected_claims, "Each verdict names its claim")
        finally:
            stop(server, thread)
        calls.clear()
        server, thread = serve([GOOD])
        try:
            clean = candidate.faithfulness(ask(server, QUESTION, PASSAGES), PASSAGES, judge)
            require(clean["supported"] == 2 and clean["total"] == 2 and abs(Fraction(str(clean["score"])) - 1) <= Fraction(1, 10**9), f"A clean answer scores 2/2, got {clean!r}")
            return f"Fabricated claim about {TOKEN}: 2/3 supported, score {float(Fraction(2, 3)):.4f}; clean answer 2/2. Recomputed from the scripted judge's verdicts."
        finally:
            stop(server, thread)
    check("Faithfulness is supported claims over total claims from the judge's per-claim verdicts", faithfulness)

    def abstention_score():
        calls = []
        server, thread = serve([REFUSAL])
        try:
            result = ask(server, QUESTION, PASSAGES)
            report = candidate.faithfulness(result, PASSAGES, lambda claim, passages: calls.append(claim) or True)
            require(report["supported"] == 0 and report["total"] == 0, f"An abstention has no claims: expected 0/0, got {report['supported']}/{report['total']}")
            require(report["score"] is None, f"score is None when there is no claim, got {report['score']!r}")
            require(calls == [], "The judge is never called for an abstention")
            return "Abstention: 0 claims, score None, judge not called."
        finally:
            stop(server, thread)
    check("An abstention has no claims, a score of None and never reaches the judge", abstention_score)

    def transfer():
        conflicts = candidate.reconcile(VERSIONS)
        require(isinstance(conflicts, list) and len(conflicts) == 1, f"reconcile must list exactly one conflicting document, got {conflicts!r}")
        require(conflicts[0].get("doc") == "runbook-relay" and conflicts[0].get("ids") == [V1, V2], f"The conflict names the document and its ids by ascending version [{V1}, {V2}], got {conflicts[0]!r}")
        require(candidate.reconcile(PASSAGES) == [], "Four passages from four documents have no conflict")
        server, thread = serve([ONLY_V2, BOTH])
        try:
            result = ask(server, CONFLICT_QUESTION, VERSIONS, max_retries=1)
            require(result["status"] == "answered" and result["attempts"] == 2, f"Citing one version only is rejected; the answer that cites both is accepted on the retry: got {result['status']!r} after {result['attempts']} ({result.get('reason')!r})")
            require({citation["passage_id"] for citation in result["citations"]} == {V1, V2}, f"Both versions must be cited, got {citation_pairs(result)!r}")
            retry_text = message_text(server.requests[1])
            require(V1 in retry_text and V2 in retry_text, "The retry names both version ids")
            require(result.get("conflicts") and result["conflicts"][0].get("ids") == [V1, V2], "The result carries the conflicts from reconcile")
        finally:
            stop(server, thread)
        server, thread = serve([ONLY_V1])
        try:
            result = ask(server, CONFLICT_QUESTION, VERSIONS, max_retries=1)
            require(result["status"] == "abstained" and result["attempts"] == 2, f"Silently picking one version twice must end abstained after two requests, got {result['status']!r} after {result['attempts']}")
            require(V1 in result["reason"] and V2 in result["reason"], f"The abstention names both version ids, got {result['reason']!r}")
            return f"runbook-relay v1 ({WAIT_V1} s) and v2 ({WAIT_V2} s): cited together or abstained naming [{V1}] and [{V2}]; never one alone."
        finally:
            stop(server, thread)
    check("Transfer: two versions of one runbook are both cited, or the answer abstains naming both", transfer)

    def offsets():
        server, thread = serve([GOOD])
        try:
            result = ask(server, QUESTION, PASSAGES)
            lookup = {passage["id"]: normalize(passage["text"]) for passage in PASSAGES}
            for citation in result["citations"]:
                start, end = citation.get("start"), citation.get("end")
                require(type(start) is int and type(end) is int, f"Each citation carries integer start and end offsets, got {citation!r}")
                require(lookup[citation["passage_id"]][start:end] == citation["quote"], f"normalized passage[{start}:{end}] must equal the quote, got {lookup[citation['passage_id']][start:end]!r}")
            return "Every quote located by character offsets in the whitespace-normalized passage."
        finally:
            stop(server, thread)
    check("bonus: every citation locates its quote by character offsets in the normalized passage", offsets, optional=True)

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
        started = time.perf_counter()
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
        parts = []
        requests = 1
        for label, question in LIVE_QUESTIONS:
            result = candidate.answer(question, LIVE_PASSAGES, base_url=base_url, model=model, max_tokens=int(config.get("max_tokens") or 400), max_retries=1)
            require(isinstance(result, dict) and result.get("status") in ("answered", "abstained"), f"The live result must be answered or abstained, got {result!r}"[:300])
            requests += int(result.get("attempts") or 0)
            if result["status"] == "answered":
                valid = valid_citations(result, LIVE_PASSAGES)
                require(len(valid) == len(result["citations"]), f"An answered live result carries only validated citations; Verify rejects {len(result['citations']) - len(valid)} of {len(result['citations'])}: {result['citations']!r}"[:600])
                parts.append(f"Q ({label}): answered, {len(result['citations'])} citation{'s' if len(result['citations']) != 1 else ''}, {len(valid)}/{len(result['citations'])} verbatim, {len(result.get('claims') or [])} claims, {result.get('attempts')} request{'s' if result.get('attempts') != 1 else ''}")
            else:
                require(result.get("citations") == [], "An abstention never carries citations")
                parts.append(f"Q ({label}): abstained after {result.get('attempts')} request{'s' if result.get('attempts') != 1 else ''}")
        seconds = time.perf_counter() - started
        return f"Live: {model} at {base_url}; {requests} requests in {seconds:.1f} s. " + "; ".join(parts) + ". Citation validity is enforced by your code; whether the model answered or abstained is a measurement of one run, not a verdict on the model."

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
        CHECKS.append({"name": "Live run: citation validity and abstention on two questions", "passed": True, "detail": live_bounded()})
    except EnvironmentBlocked as blocked:
        CHECKS.append({"name": "Environment blocked", "passed": False, "detail": str(blocked)[:1500]})
    except Exception as error:
        CHECKS.append({"name": "Live run: citation validity and abstention on two questions", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})


try:
    trial()
except Exception as error:
    CHECKS.append({"name": "Load answer module", "passed": False, "detail": f"{type(error).__name__}: {error}"[:1500]})
print(json.dumps({"checks": CHECKS}))
sys.exit(0 if CHECKS and all(item["passed"] for item in CHECKS if not item.get("optional")) else 1)
