#!/usr/bin/env python3
"""Report-only style scan for the `humanize` command. Never edits files.

Usage:
  style_scan.py --project ID [--root DIR] [--json]
  style_scan.py --file report.md [--json]

Measures predictability signals that detectors and human reviewers react to (see references/humanize.md):
sentence-length spread (burstiness proxy), paragraph-length spread, stock AI vocabulary, copula avoidance,
negative parallelism, trailing "-ing" significance clauses, rule-of-three lists, em-dash density, bold density,
and paragraph-closing summary sentences. Code, math, tables, headings, figures and citations are ignored.
These are heuristics, not an AI-detector score. Exit codes: 0 ok, 2 usage/IO problem.
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ms_common as C  # noqa: E402
import ms_state as S  # noqa: E402

TELL_WORDS = [
    "delve", "delves", "delving", "tapestry", "pivotal", "underscore", "underscores", "underscoring", "testament",
    "showcase", "showcases", "showcasing", "landscape", "realm", "multifaceted", "intricate", "crucial", "vital",
    "seamless", "seamlessly", "robust", "leverage", "leverages", "leveraging", "foster", "fosters", "fostering",
    "navigate", "navigating", "embark", "unlock", "unleash", "holistic", "myriad", "plethora", "meticulous",
    "noteworthy", "invaluable", "paramount", "transformative", "cutting-edge", "game-changer", "ever-evolving",
    "enhance", "enhances", "streamline", "comprehensive", "encompassing", "valuable insight", "key turning point",
]
TELL_PHRASES = [
    r"it is (?:important|worth|essential|crucial) to (?:note|mention|highlight|emphasi[sz]e)",
    r"in today's (?:\w+ ){0,2}(?:world|landscape|era)", r"plays? a (?:crucial|vital|pivotal|key|significant) role",
    r"in (?:conclusion|summary)\b", r"marking a (?:pivotal|significant) (?:moment|shift)", r"stands? as a testament",
    r"not only\b.{1,80}\bbut also\b", r"\bit'?s not\b.{1,60}[,;]\s*it'?s\b", r"\bis not (?:just|merely|simply)\b",
    r"despite (?:these|its) challenges", r"experts (?:argue|say|believe)", r"has been (?:widely )?(?:cited|noted)",
]
COPULA_RE = re.compile(r"\b(?:serves as|stands as|acts as|boasts|features|represents a)\b", re.I)
ING_TAIL_RE = re.compile(r",\s+(?:highlighting|underscoring|showcasing|reflecting|emphasi[sz]ing|demonstrating|"
                         r"illustrating|contributing to|ensuring|fostering)\b[^.]*\.", re.I)
TRIPLE_RE = re.compile(r"\b[\w-]+(?: [\w-]+)?, [\w-]+(?: [\w-]+)?,? and [\w-]+(?: [\w-]+)?\b")
CLOSER_RE = re.compile(r"^(?:overall|in (?:conclusion|summary)|ultimately|in essence|to sum up|thus|therefore|"
                       r"these (?:findings|results) (?:highlight|underscore|demonstrate|show))\b", re.I)
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
ABBREV_RE = re.compile(r"\b(?:e\.g|i\.e|et al|vs|Fig|Eq|Sec|approx|cf|No|Dr|Prof)\.$")


def prose_paragraphs(text):
    """Return prose paragraphs only: no front matter, code, math, tables, headings, figures, lists, references."""
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            text = text[end + 4:]
    text = C.strip_code(text)
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    m = re.search(r"^#\s+References\s*$", text, flags=re.M)
    if m:
        text = text[:m.start()]
    paras = []
    for block in re.split(r"\n\s*\n", text):
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines or all(re.match(r"\s*(#|\||!\[|[-*+]\s|\d+[.)]\s|:|Table:|>)", l) for l in lines):
            continue
        b = " ".join(l.strip() for l in lines if not l.lstrip().startswith(("#", "|", "![")))
        b = re.sub(r"\[[^\]]*@[^\]]*\]", "", b)           # citations
        b = re.sub(r"\[\[[^\]]*\]\]", "", b)              # evidence markers
        b = re.sub(r"\$[^$\n]+\$", "MATH", b)
        b = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", b)
        if len(b.split()) >= 8:
            paras.append(b.strip())
    return paras


def sentences(par):
    out, buf = [], ""
    for piece in SENT_SPLIT_RE.split(par):
        buf = (buf + " " + piece).strip() if buf else piece
        if ABBREV_RE.search(buf):
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def stats(xs):
    if not xs:
        return {"n": 0, "mean": 0.0, "std": 0.0, "cv": 0.0}
    mean = sum(xs) / len(xs)
    std = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
    return {"n": len(xs), "mean": round(mean, 1), "std": round(std, 1), "cv": round(std / mean, 2) if mean else 0.0}


def scan(text):
    paras = prose_paragraphs(text)
    sents = [s for p in paras for s in sentences(p)]
    slen = [len(s.split()) for s in sents]
    plen = [len(p.split()) for p in paras]
    words = sum(plen) or 1
    low = " ".join(paras).lower()
    tells = {}
    for w in TELL_WORDS:
        n = len(re.findall(r"\b%s\b" % re.escape(w), low))
        if n:
            tells[w] = n
    phrases = {}
    for p in TELL_PHRASES:
        n = len(re.findall(p, low))
        if n:
            phrases[p] = n
    joined = " ".join(paras)
    closers = sum(1 for p in paras if sentences(p) and CLOSER_RE.match(sentences(p)[-1]))
    par_flags = []
    for i, p in enumerate(paras, 1):
        ss = sentences(p)
        if len(ss) >= 4:
            sl = [len(s.split()) for s in ss]
            if stats(sl)["cv"] < 0.25:
                par_flags.append({"paragraph": i, "start": p[:60], "reason": "sentences nearly uniform in length"})
    res = {
        "words": words,
        "sentence_length": stats(slen),
        "paragraph_length": stats(plen),
        "short_sentences_le8": sum(1 for x in slen if x <= 8),
        "long_sentences_ge30": sum(1 for x in slen if x >= 30),
        "tell_words": tells,
        "tell_phrases": phrases,
        "copula_avoidance": len(COPULA_RE.findall(joined)),
        "ing_significance_tails": len(ING_TAIL_RE.findall(joined)),
        "rule_of_three_lists": len(TRIPLE_RE.findall(joined)),
        "em_dashes_per_1000_words": round(1000 * (joined.count("—") + joined.count(" -- ")) / words, 1),
        "bold_spans_per_1000_words": round(1000 * len(re.findall(r"\*\*[^*]+\*\*", joined)) / words, 1),
        "summary_closer_paragraphs": closers,
        "uniform_paragraphs": par_flags,
    }
    res["findings"] = findings(res)
    return res


def findings(r):
    out = []
    sl = r["sentence_length"]
    if sl["n"] >= 15 and sl["cv"] < 0.45:
        out.append("Sentence lengths are uniform (CV %.2f; varied prose is usually 0.5-0.8). Vary rhythm: merge, split, add a short sentence." % sl["cv"])
    if sum(r["tell_words"].values()) / max(r["words"], 1) * 1000 > 3:
        out.append("Stock AI vocabulary is DENSE (%s; over 3 per 1000 words). Read these spots again and prefer plain, specific words "
                   "where they are filler; keep any that are real source terminology (e.g. 'robust regression', 'fitness landscape')." % ", ".join(sorted(r["tell_words"])))
    elif r["tell_words"]:
        out.append("Possible stock vocabulary (only worth a second look; may be correct source terminology, do not replace blindly): %s." % ", ".join(sorted(r["tell_words"])))
    if r["tell_phrases"]:
        out.append("Template phrases found (%d patterns): negative parallelism, 'it is important to note', 'in conclusion', etc." % len(r["tell_phrases"]))
    if r["copula_avoidance"]:
        out.append("'serves as / boasts / represents a' x%d: prefer 'is' / 'has'." % r["copula_avoidance"])
    if r["ing_significance_tails"]:
        out.append("Trailing significance clauses (', highlighting ...') x%d: cut or state the actual consequence." % r["ing_significance_tails"])
    if r["rule_of_three_lists"] > max(3, r["words"] // 400):
        out.append("Many three-item lists (%d): keep only those whose items are really three." % r["rule_of_three_lists"])
    if r["em_dashes_per_1000_words"] > 4:
        out.append("Em dashes are heavy (%.1f per 1000 words)." % r["em_dashes_per_1000_words"])
    if r["bold_spans_per_1000_words"] > 6:
        out.append("Heavy boldface in prose (%.1f per 1000 words)." % r["bold_spans_per_1000_words"])
    if r["summary_closer_paragraphs"] >= 3:
        out.append("%d paragraphs end with a summarising sentence ('Overall', 'In summary'): drop most of them." % r["summary_closer_paragraphs"])
    if r["uniform_paragraphs"]:
        out.append("%d paragraph(s) have near-identical sentence lengths." % len(r["uniform_paragraphs"]))
    pl = r["paragraph_length"]
    if pl["n"] >= 8 and pl["cv"] < 0.25:
        out.append("Paragraph lengths are uniform (CV %.2f)." % pl["cv"])
    return out


def to_text(r):
    sl, pl = r["sentence_length"], r["paragraph_length"]
    lines = ["Style scan (heuristic, not an AI-detector score)",
             "  words: %d   sentences: %d   paragraphs: %d" % (r["words"], sl["n"], pl["n"]),
             "  sentence length: mean %.1f, std %.1f, CV %.2f (<=8 words: %d, >=30 words: %d)" % (
                 sl["mean"], sl["std"], sl["cv"], r["short_sentences_le8"], r["long_sentences_ge30"]),
             "  paragraph length: mean %.1f, CV %.2f" % (pl["mean"], pl["cv"]),
             "  tell words: %s" % (", ".join("%s x%d" % kv for kv in sorted(r["tell_words"].items())) or "none"),
             "  em dashes/1000w: %.1f   bold/1000w: %.1f   -ing tails: %d   rule-of-three: %d" % (
                 r["em_dashes_per_1000_words"], r["bold_spans_per_1000_words"], r["ing_significance_tails"], r["rule_of_three_lists"]),
             "Findings:"]
    lines += ["  - " + f for f in r["findings"]] or ["  - none"]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--file"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        root = os.path.abspath(a.root)
        path = a.file or S.artifact_path(root, S.resolve(root, a.project), "draft")
        if not os.path.isfile(path):
            print("ERROR: file not found: %s" % path, file=sys.stderr)
            return 2
        res = scan(C.read_text(path))
    except (S.StateError, OSError) as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    print(json.dumps(res, indent=2) if a.json else to_text(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
