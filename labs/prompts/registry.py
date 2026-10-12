"""Prompt registry for the operator assistant.

Starter: templates live in files and carry version ids, but nothing binds a version to its
text, and the operator's request is pasted straight into the instructions. See LEARN.md for
the complete contract that Verify checks.
"""
import hashlib
import json
import os
import urllib.request


class RegistryError(Exception):
    """A template, version or variable set that cannot be trusted."""


class Registry:
    def __init__(self, root):
        self.root = root

    def _entries(self):
        with open(os.path.join(self.root, "index.json"), encoding="utf-8") as handle:
            return json.load(handle)["templates"]

    def _path(self, entry):
        return os.path.join(self.root, *entry["file"].split("/"))

    def verify(self):
        catalog = {}
        for entry in self._entries():
            path = self._path(entry)
            if not os.path.exists(path):
                raise RegistryError(f"{entry['name']} {entry['version']}: missing file {entry['file']}")
            with open(path, "rb") as handle:
                catalog.setdefault(entry["name"], {})[entry["version"]] = hashlib.sha256(handle.read()).hexdigest()
        return catalog

    def _template(self, name, version):
        for entry in self._entries():
            if entry["name"] == name and entry["version"] == version:
                with open(self._path(entry), encoding="utf-8") as handle:
                    return handle.read()
        raise RegistryError(f"{name} {version}: unknown template version")

    def render(self, name, version, variables):
        text = self._template(name, version)
        for key, value in variables.items():
            text = text.replace("{{" + key + "}}", value)
        return text

    def call(self, name, version, variables, *, base_url, model, params, log_path):
        rendered = self.render(name, version, variables)
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": rendered}], "max_tokens": params.get("max_tokens", 64)}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        record = {"prompt": name, "version": version, "model": model, "output": payload["choices"][0]["message"]["content"]}
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")
        return record

    def replay(self, record):
        return self.render(record["prompt"], record["version"], record.get("variables", {}))
