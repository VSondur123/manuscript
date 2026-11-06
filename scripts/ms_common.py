"""Shared helpers for ManuScript scripts. Standard library only (Python 3.9+)."""
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

SCHEMA_VERSION = 1


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def which(tool):
    return shutil.which(tool)


def eprint(*a):
    print(*a, file=sys.stderr)


# ---- minimal YAML subset: nested maps, lists of scalars, inline lists, scalars, comments ----

def _scalar(v):
    v = v.strip()
    if v == "":
        return None
    if v[0] in "\"'" and v[-1] == v[0] and len(v) >= 2:
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [] if not inner else [_scalar(x) for x in inner.split(",")]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d+\.\d+", v):
        return float(v)
    return v


def _strip_comment(line):
    out, q = [], None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def parse_yaml(text):
    """Parse the restricted YAML subset used by ManuScript config/doctype files."""
    lines = []
    for raw in text.splitlines():
        s = _strip_comment(raw)
        if s.strip():
            lines.append((len(s) - len(s.lstrip(" ")), s.strip()))
    pos = [0]

    def block(indent):
        if pos[0] >= len(lines):
            return None
        if lines[pos[0]][1].startswith("- "):
            res = []
            while pos[0] < len(lines) and lines[pos[0]][0] == indent and lines[pos[0]][1].startswith("- "):
                res.append(_scalar(lines[pos[0]][1][2:]))
                pos[0] += 1
            return res
        res = {}
        while pos[0] < len(lines) and lines[pos[0]][0] == indent:
            content = lines[pos[0]][1]
            if ":" not in content:
                raise ValueError("Invalid YAML line: %r" % content)
            key, _, val = content.partition(":")
            key = key.strip()
            pos[0] += 1
            if val.strip() == "":
                if pos[0] < len(lines) and (lines[pos[0]][0] > indent or
                        (lines[pos[0]][0] == indent and lines[pos[0]][1].startswith("- "))):
                    res[key] = block(lines[pos[0]][0])
                else:
                    res[key] = None
            else:
                res[key] = _scalar(val)
        return res

    if not lines:
        return {}
    return block(lines[0][0])


def load_yaml(path):
    return parse_yaml(read_text(path))


def strip_code(text):
    """Blank out fenced code blocks and inline code so structural checks ignore them."""
    text = re.sub(r"^(```|~~~).*?^\1[ \t]*$", lambda m: "\n" * m.group(0).count("\n"),
                  text, flags=re.S | re.M)
    return re.sub(r"`[^`\n]*`", "``", text)
