"""Prompt registry: template files on disk, index.json bound to content hashes, regex rendering, urllib transport."""
import hashlib
import json
import os
import re
import urllib.request

SLOT = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
SEPARATOR = "\n---\n"


class RegistryError(Exception):
    """A template, version or variable set that cannot be trusted."""


def normalize(text):
    return text.replace("\r\n", "\n").rstrip("\n")


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def escape(value):
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def substitute(template, variables):
    slots = set(SLOT.findall(template))
    if slots != set(variables):
        raise RegistryError(f"variables {sorted(variables)} do not match the template slots {sorted(slots)}")
    for key, value in variables.items():
        if not isinstance(value, str):
            raise RegistryError(f"variable {key!r} must be a string")
    # One pass: a value is never scanned for slots, so "{{request}}" inside a value stays literal.
    return SLOT.sub(lambda match: f"<{match.group(1)}>{escape(variables[match.group(1)])}</{match.group(1)}>", template)


def split(template):
    if SEPARATOR not in template:
        return None, template
    system, user = template.split(SEPARATOR, 1)
    if SLOT.search(system):
        raise RegistryError("a slot before the --- separator would put request data into the instructions")
    return system, user


class Registry:
    def __init__(self, root):
        self.root = root

    def _entries(self):
        with open(os.path.join(self.root, "index.json"), encoding="utf-8") as handle:
            index = json.load(handle)
        entries = index.get("templates") if isinstance(index, dict) else None
        if not isinstance(entries, list):
            raise RegistryError("index.json must hold a list under 'templates'")
        return entries

    def _read(self, entry):
        path = os.path.join(self.root, *entry["file"].split("/"))
        try:
            with open(path, encoding="utf-8") as handle:
                return normalize(handle.read())
        except OSError as error:
            raise RegistryError(f"{entry['name']} {entry['version']}: template file {entry['file']} cannot be read ({error})") from None

    def _checked(self, entry):
        text = self._read(entry)
        digest = sha256(text)
        if digest != entry["sha256"]:
            raise RegistryError(f"{entry['name']} {entry['version']}: template text changed under an unchanged version (index {entry['sha256'][:12]}, file {digest[:12]})")
        return text

    def verify(self):
        catalog = {}
        by_digest = {}
        for entry in self._entries():
            name, version = entry["name"], entry["version"]
            if version in catalog.get(name, {}):
                raise RegistryError(f"{name} {version}: two index entries share one version")
            digest = sha256(self._checked(entry))
            twin = by_digest.get((name, digest))
            if twin is not None:
                raise RegistryError(f"{name} {twin} and {name} {version}: two versions carry the same text")
            by_digest[(name, digest)] = version
            catalog.setdefault(name, {})[version] = digest
        return catalog

    def _template(self, name, version):
        matches = [entry for entry in self._entries() if entry.get("name") == name and entry.get("version") == version]
        if not matches:
            raise RegistryError(f"{name} {version}: unknown template version")
        if len(matches) > 1:
            raise RegistryError(f"{name} {version}: two index entries share one version")
        return self._checked(matches[0])

    def _render(self, name, version, variables):
        template = self._template(name, version)
        system, user = split(template)
        rendered_user = substitute(user, variables)
        if system is None:
            return rendered_user, sha256(template), [{"role": "user", "content": rendered_user}]
        rendered = system + SEPARATOR + rendered_user
        return rendered, sha256(template), [{"role": "system", "content": system}, {"role": "user", "content": rendered_user}]

    def render(self, name, version, variables):
        return self._render(name, version, variables)[0]

    def call(self, name, version, variables, *, base_url, model, params, log_path):
        rendered, template_digest, messages = self._render(name, version, variables)
        body = json.dumps({"model": model, "messages": messages, **params}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("LLM_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        record = {
            "prompt": name, "version": version, "template_sha256": template_digest,
            "model": model, "params": dict(params), "variables": dict(variables),
            "rendered_sha256": sha256(rendered), "output": payload["choices"][0]["message"]["content"],
        }
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")
        return record

    def replay(self, record):
        rendered, template_digest, _ = self._render(record["prompt"], record["version"], record["variables"])
        if template_digest != record["template_sha256"]:
            raise RegistryError(f"{record['prompt']} {record['version']}: the registry now holds {template_digest[:12]}, the log was made with {record['template_sha256'][:12]}")
        if sha256(rendered) != record["rendered_sha256"]:
            raise RegistryError(f"{record['prompt']} {record['version']}: the re-rendered text does not hash to the logged rendered_sha256")
        return rendered
