"""Prompt registry: the index loaded into an in-memory SQLite table, a hand-written slot scanner, http.client transport."""
from __future__ import annotations

import hashlib
import html
import http.client
import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

SLOT = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
SEPARATOR = "\n---\n"


class RegistryError(Exception):
    pass


@dataclass
class Record:
    prompt: str
    version: str
    template_sha256: str
    model: str
    params: dict
    variables: dict
    rendered_sha256: str
    output: str


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def scan(template: str, variables: dict) -> str:
    """Walk the template once, copying text and emitting a delimited block at each slot."""
    parts, position, used = [], 0, set()
    for match in SLOT.finditer(template):
        key = match.group(1)
        if key not in variables:
            raise RegistryError(f"slot {key!r} has no variable")
        if not isinstance(variables[key], str):
            raise RegistryError(f"variable {key!r} must be a string")
        parts.append(template[position:match.start()])
        parts.append(f"<{key}>{html.escape(variables[key], quote=False)}</{key}>")
        position = match.end()
        used.add(key)
    parts.append(template[position:])
    unused = set(variables) - used
    if unused:
        raise RegistryError(f"variables {sorted(unused)} have no slot in the template")
    return "".join(parts)


class Registry:
    def __init__(self, root: str):
        self.root = root
        self.table = sqlite3.connect(":memory:")
        self.table.execute("CREATE TABLE templates (name TEXT NOT NULL, version TEXT NOT NULL, file TEXT NOT NULL, sha256 TEXT NOT NULL, text TEXT, UNIQUE(name, version))")
        self.problem: RegistryError | None = None
        try:
            self._load()
        except RegistryError as error:
            self.problem = error

    def _load(self) -> None:
        with open(os.path.join(self.root, "index.json"), encoding="utf-8") as handle:
            entries = json.load(handle)["templates"]
        for entry in entries:
            try:
                self.table.execute("INSERT INTO templates (name, version, file, sha256) VALUES (?, ?, ?, ?)", (entry["name"], entry["version"], entry["file"], entry["sha256"]))
            except sqlite3.IntegrityError:
                raise RegistryError(f"{entry['name']} {entry['version']}: two index entries share one version") from None
        for name, version, file in self.table.execute("SELECT name, version, file FROM templates").fetchall():
            path = os.path.join(self.root, *file.split("/"))
            try:
                with open(path, "rb") as handle:
                    text = handle.read().decode("utf-8").replace("\r\n", "\n").rstrip("\n")
            except OSError:
                text = None
            self.table.execute("UPDATE templates SET text = ? WHERE name = ? AND version = ?", (text, name, version))

    def _checked(self, name: str, version: str, text: str | None, expected: str) -> str:
        if text is None:
            raise RegistryError(f"{name} {version}: template file cannot be read")
        if digest(text) != expected:
            raise RegistryError(f"{name} {version}: template text changed under an unchanged version")
        return text

    def verify(self) -> dict:
        if self.problem is not None:
            raise self.problem
        catalog: dict = {}
        for name, version, sha, text in self.table.execute("SELECT name, version, sha256, text FROM templates ORDER BY rowid"):
            self._checked(name, version, text, sha)
            catalog.setdefault(name, {})[version] = sha
        twins = self.table.execute("SELECT name, group_concat(version, ' ') FROM (SELECT name, version, sha256 FROM templates ORDER BY name, version) GROUP BY name, sha256 HAVING count(*) > 1").fetchall()
        if twins:
            name, versions = twins[0]
            raise RegistryError(f"{name} {versions}: two versions carry the same text")
        return catalog

    def _template(self, name: str, version: str) -> tuple[str, str]:
        if self.problem is not None:
            raise self.problem
        row = self.table.execute("SELECT text, sha256 FROM templates WHERE name = ? AND version = ?", (name, version)).fetchone()
        if row is None:
            raise RegistryError(f"{name} {version}: unknown template version")
        return self._checked(name, version, row[0], row[1]), row[1]

    def _messages(self, name: str, version: str, variables: dict) -> tuple[str, str, list]:
        template, sha = self._template(name, version)
        if SEPARATOR not in template:
            rendered = scan(template, variables)
            return rendered, sha, [{"role": "user", "content": rendered}]
        system, user = template.split(SEPARATOR, 1)
        if SLOT.search(system):
            raise RegistryError(f"{name} {version}: a slot in the instruction section would turn data into instructions")
        rendered_user = scan(user, variables)
        return system + SEPARATOR + rendered_user, sha, [{"role": "system", "content": system}, {"role": "user", "content": rendered_user}]

    def render(self, name: str, version: str, variables: dict) -> str:
        return self._messages(name, version, variables)[0]

    def call(self, name: str, version: str, variables: dict, *, base_url: str, model: str, params: dict, log_path: str) -> dict:
        rendered, sha, messages = self._messages(name, version, variables)
        body = dict(params)
        body.update({"model": model, "messages": messages})
        payload = self._post(base_url, body)
        record = Record(name, version, sha, model, dict(params), dict(variables), digest(rendered), payload["choices"][0]["message"]["content"])
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(json.dumps(asdict(record)) + "\n")
        return asdict(record)

    @staticmethod
    def _post(base_url: str, body: dict) -> dict:
        url = urlsplit(base_url.rstrip("/") + "/chat/completions")
        connection = (http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection)(url.hostname, url.port, timeout=60)
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            connection.request("POST", url.path, body=json.dumps(body).encode("utf-8"), headers=headers)
            response = connection.getresponse()
            raw = response.read()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {raw[:200]!r}")
            return json.loads(raw.decode("utf-8"))
        finally:
            connection.close()

    def replay(self, record: dict) -> str:
        rendered, sha, _ = self._messages(record["prompt"], record["version"], record["variables"])
        if sha != record["template_sha256"]:
            raise RegistryError(f"{record['prompt']} {record['version']}: registry text {sha[:12]} is not the logged {record['template_sha256'][:12]}")
        if digest(rendered) != record["rendered_sha256"]:
            raise RegistryError(f"{record['prompt']} {record['version']}: re-rendered text does not hash to rendered_sha256")
        return rendered
