"""A small JSON Schema (draft 2020-12) validator for spec kinds, so the client needs no `jsonschema` package.

Supported: type (incl. lists of types, "integer" vs "number"), properties, required, additionalProperties (bool or a
schema), patternProperties, items (a schema), prefixItems, minItems/maxItems, enum, const, minimum/maximum,
exclusiveMinimum/exclusiveMaximum, minLength/maxLength, pattern, oneOf/anyOf/allOf/not, $ref to "#/$defs/..." (and
"#/definitions/..."), default (read by defaults()). Unknown keywords are ignored. Errors come back as
[(path, message, candidates)] with "did you mean" candidates for a misspelt property or enum value.
"""
from __future__ import annotations

import difflib
import re

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool) or (isinstance(v, float) and v.is_integer()),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _close(word, names) -> list:
    return difflib.get_close_matches(str(word), [str(n) for n in names], n=3, cutoff=0.5)


def _resolve(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"only local $refs are supported: {ref}")
    node = root
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _path(p: str) -> str:
    return p or "(top)"


def validate(value, schema: dict, root: dict | None = None, path: str = "") -> list:
    root = root if root is not None else schema
    if schema is True or schema == {}:
        return []
    if schema is False:
        return [(_path(path), "not allowed here", [])]
    if "$ref" in schema:
        errs = validate(value, _resolve(root, schema["$ref"]), root, path)
        rest = {k: v for k, v in schema.items() if k != "$ref"}
        return errs + (validate(value, rest, root, path) if rest else [])
    errs: list = []
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES.get(x, lambda v: True)(value) for x in types):
            return [(_path(path), f"should be {' or '.join(types)}, not {type(value).__name__} {value!r}"[:200], [])]
    if "const" in schema and value != schema["const"]:
        errs.append((_path(path), f"should be {schema['const']!r}", []))
    if "enum" in schema and value not in schema["enum"]:
        errs.append((_path(path), f"{value!r} is not one of {', '.join(map(repr, schema['enum']))}",
                     _close(value, schema["enum"])))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for k, ok, word in (("minimum", lambda a, b: a >= b, ">="), ("maximum", lambda a, b: a <= b, "<="),
                            ("exclusiveMinimum", lambda a, b: a > b, ">"), ("exclusiveMaximum", lambda a, b: a < b, "<")):
            if k in schema and not ok(value, schema[k]):
                errs.append((_path(path), f"{value} should be {word} {schema[k]}", []))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append((_path(path), f"shorter than {schema['minLength']}", []))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errs.append((_path(path), f"longer than {schema['maxLength']}", []))
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append((_path(path), f"{value!r} does not match {schema['pattern']}", []))
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append((_path(path), f"needs at least {schema['minItems']} items", []))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append((_path(path), f"takes at most {schema['maxItems']} items", []))
        pre = schema.get("prefixItems") or []
        for i, (v, s) in enumerate(zip(value, pre)):
            errs += validate(v, s, root, f"{path}[{i}]")
        if isinstance(schema.get("items"), dict):
            for i, v in enumerate(value[len(pre):], start=len(pre)):
                errs += validate(v, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append((_path(path), f"needs {k!r}" + (f" ({props[k].get('description')})"
                                                            if isinstance(props.get(k), dict) and props[k].get("description") else ""), []))
        pats = schema.get("patternProperties", {})
        addl = schema.get("additionalProperties", True)
        for k, v in value.items():
            sub = f"{path}.{k}" if path else k
            if k in props:
                errs += validate(v, props[k], root, sub)
                continue
            matched = [s for p, s in pats.items() if re.search(p, k)]
            for s in matched:
                errs += validate(v, s, root, sub)
            if matched:
                continue
            if addl is False:
                errs.append((sub, f"unknown field {k!r}", _close(k, props)))
            elif isinstance(addl, dict):
                errs += validate(v, addl, root, sub)
    for k in ("allOf",):
        for s in schema.get(k, []):
            errs += validate(value, s, root, path)
    if "anyOf" in schema:
        if all(validate(value, s, root, path) for s in schema["anyOf"]):
            errs.append((_path(path), "matches none of the allowed forms (anyOf)", []))
    if "oneOf" in schema:
        n = sum(1 for s in schema["oneOf"] if not validate(value, s, root, path))
        if n != 1:
            errs.append((_path(path), f"should match exactly one form (oneOf), matches {n}", []))
    if "not" in schema and not validate(value, schema["not"], root, path):
        errs.append((_path(path), "matches a form that is not allowed", []))
    return errs


def defaults(value: dict, schema: dict, root: dict | None = None) -> dict:
    """value with the top-level properties' defaults filled in (a shallow pass: nested objects keep theirs)."""
    root = root if root is not None else schema
    if "$ref" in schema:
        schema = _resolve(root, schema["$ref"])
    out = dict(value)
    for k, s in (schema.get("properties") or {}).items():
        if k not in out and isinstance(s, dict) and "default" in s:
            out[k] = s["default"]
    return out
