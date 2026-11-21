#!/usr/bin/env python3
"""Parser/serializzatore minimo di S-expression (file KiCad e Specctra DSN). Modulo per gli altri script.

Le stringhe tra virgolette diventano oggetti Q (sottoclasse di str), così in uscita restano tra virgolette.
"""
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


class Q(str):
    """Stringa che va scritta tra virgolette."""


def parse(text: str):
    stack, cur = [], []
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError(f"S-expression non valida vicino a: {text[pos:pos + 40]!r}")
        pos = m.end()
        if m.group(1):
            stack.append(cur)
            cur = []
        elif m.group(2):
            if not stack:
                raise ValueError("parentesi chiusa in eccesso")
            done = cur
            cur = stack.pop()
            cur.append(done)
        elif m.group(3) is not None:
            cur.append(Q(m.group(3).replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")))
        else:
            cur.append(m.group(4))
    if stack:
        raise ValueError("parentesi non bilanciate")
    return cur[0] if len(cur) == 1 else cur


def _atom(x) -> str:
    if isinstance(x, Q):
        return '"' + x.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        s = f"{x:.4f}".rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(x)


def dumps(e, indent: int = 0) -> str:
    if not isinstance(e, list):
        return _atom(e)
    if not any(isinstance(c, list) for c in e):
        return "(" + " ".join(_atom(c) for c in e) + ")"
    pad = "\t" * (indent + 1)
    head = []
    i = 0
    while i < len(e) and not isinstance(e[i], list):
        head.append(_atom(e[i]))
        i += 1
    parts = ["(" + " ".join(head)]
    for c in e[i:]:
        parts.append("\n" + pad + dumps(c, indent + 1))
    return "".join(parts) + "\n" + "\t" * indent + ")"


def find(e, key):
    """Primo figlio lista con testa = key."""
    for c in e:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def find_all(e, key):
    return [c for c in e if isinstance(c, list) and c and c[0] == key]


def walk(e):
    yield e
    for c in e:
        if isinstance(c, list):
            yield from walk(c)
