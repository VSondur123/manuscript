#!/usr/bin/env python3
"""ManuScript project state engine: init, status, verify, sync, stage, backup, approvals.

Workspace layout (per document project, under <root>/manuscript/<project-id>/):
  Visible (the user's files):  plan.md, <project-id>-report.md, and at the end <project-id>.tex + .pdf
  Hidden internals in .ms/:    state.json, project-config.yaml, evidence-inventory.md, references.bib,
                               approved/, history/, latex/, logs/, validation/, figures/, figures-src/, data/
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ms_common import SCHEMA_VERSION, load_yaml, now, read_json, sha256_file, write_json  # noqa: E402

STAGES = [
    "INITIALISED", "DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL",
    "PLAN_APPROVED", "EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION",
    "MARKDOWN_PENDING_APPROVAL", "MARKDOWN_APPROVED", "LATEX_GENERATION", "LATEX_VALIDATION",
    "PDF_GENERATION", "PDF_QA", "COMPLETED",
]
IDX = {s: i for i, s in enumerate(STAGES)}
APPROVAL_PHRASES = {"plan": "APPROVE PLAN", "markdown": "APPROVE MARKDOWN"}

# Tracked artifacts: key -> path relative to the project directory
WORK = ".ms"  # hidden folder for everything except plan.md and the report
ARTIFACTS = {
    "config": WORK + "/project-config.yaml",
    "plan": "plan.md",
    "evidence": WORK + "/evidence-inventory.md",
    "draft": "{pid}-report.md",
    "bibliography": WORK + "/references.bib",
}


class StateError(Exception):
    pass


def projects_dir(root):
    return os.path.join(root, "manuscript")


def list_projects(root):
    base = projects_dir(root)
    if not os.path.isdir(base):
        return []
    return sorted(d for d in os.listdir(base) if os.path.isfile(os.path.join(base, d, WORK, "state.json")))


def resolve(root, pid):
    found = list_projects(root)
    if pid:
        if pid not in found:
            raise StateError("No project %r under %s (found: %s)" % (pid, projects_dir(root), found or "none"))
        return pid
    if len(found) == 1:
        return found[0]
    if not found:
        raise StateError("No ManuScript project found under %s" % projects_dir(root))
    raise StateError("Several projects found %s; specify one." % found)


def pdir(root, pid):
    return os.path.join(projects_dir(root), pid)


def load(root, pid):
    return read_json(os.path.join(pdir(root, pid), WORK, "state.json"))


def save(root, pid, st):
    st["updated_at"] = now()
    write_json(os.path.join(pdir(root, pid), WORK, "state.json"), st)


def artifact_path(root, pid, key):
    return os.path.join(pdir(root, pid), ARTIFACTS[key].format(pid=pid))


def file_hash(root, pid, key):
    p = artifact_path(root, pid, key)
    return sha256_file(p) if os.path.isfile(p) else None


def init_project(root, pid, doctype, title=None):
    d = pdir(root, pid)
    if os.path.exists(os.path.join(d, WORK, "state.json")):
        raise StateError("Project %r already exists" % pid)
    for sub in ("approved", "history", "latex", "logs", "validation"):
        os.makedirs(os.path.join(d, WORK, sub), exist_ok=True)
    st = {
        "schema_version": SCHEMA_VERSION,
        "project_id": pid,
        "doctype": doctype,
        "title": title,
        "stage": "INITIALISED",
        "completed_stages": [],
        "artifacts": {k: {"path": v.format(pid=pid), "sha256": None, "version": 0} for k, v in ARTIFACTS.items()},
        "plan_approval": None,
        "markdown_approval": None,
        "latex": {"path": None, "sha256": None, "version": 0},
        "pdf": {"path": None, "sha256": None, "version": 0},
        "last_validation": None,
        "outstanding_issues": [],
        "history": [{"at": now(), "from": None, "to": "INITIALISED", "note": "project created"}],
        "created_at": now(),
    }
    cfg = os.path.join(d, ARTIFACTS["config"].format(pid=pid))
    tpl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "project-config.yaml")
    if os.path.isfile(tpl) and not os.path.exists(cfg):
        text = open(tpl, encoding="utf-8").read()
        text = text.replace("project_id: my-document", "project_id: %s" % pid)
        text = text.replace("document_type: research-report ", "document_type: %s " % doctype)
        text = text.replace("title: Working Title", "title: %s" % (title or "Working Title"))
        with open(cfg, "w", encoding="utf-8") as f:
            f.write(text)
    save(root, pid, st)
    return st


def figure_dependencies(root, pid):
    """{relpath: sha256} of every local image the draft references, plus (via figures/manifest.json)
    the figure specs and input data files they were built from."""
    d = pdir(root, pid)
    draft = artifact_path(root, pid, "draft")
    deps = {}
    if not os.path.isfile(draft):
        return deps
    text = re.sub(r"^(```|~~~).*?^\1[ \t]*$", "", open(draft, encoding="utf-8", errors="replace").read(), flags=re.S | re.M)
    refs = set()
    for m in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)", text):
        rel = os.path.normpath(m.group(1))
        if not re.match(r"^[a-z]+:", m.group(1)) and os.path.isfile(os.path.join(d, rel)):
            refs.add(rel)
            deps[rel] = sha256_file(os.path.join(d, rel))
    mpath = os.path.join(d, WORK, "figures", "manifest.json")
    if os.path.isfile(mpath):
        for ent in read_json(mpath).values():
            if any(os.path.normpath(o) in refs for o in ent.get("outputs", [])):
                for rel in [ent["spec"]] + [i["path"] for i in ent.get("inputs", [])]:
                    p_ = os.path.join(d, rel)
                    deps[os.path.normpath(rel)] = sha256_file(p_) if os.path.isfile(p_) else "MISSING"
    return deps


def figure_changes(root, pid, st):
    ap = st.get("markdown_approval") or {}
    d = pdir(root, pid)
    out = []
    for rel, sha in (ap.get("figures") or {}).items():
        p_ = os.path.join(d, rel)
        cur = sha256_file(p_) if os.path.isfile(p_) else None
        if cur != sha:
            out.append({"artifact": rel, "kind": "figure_changed" if cur else "figure_missing",
                        "detail": "figure/spec/data changed after Markdown approval; re-approval required"})
    return out


def markdown_approval_status(root, pid, st):
    """Return 'none' | 'current' | 'stale' for the Markdown approval (draft text AND figures)."""
    ap = st.get("markdown_approval")
    if not ap:
        return "none"
    if file_hash(root, pid, "draft") != ap["sha256"]:
        return "stale"
    return "stale" if figure_changes(root, pid, st) else "current"


def plan_approval_status(root, pid, st):
    ap = st.get("plan_approval")
    if not ap:
        return "none"
    return "current" if file_hash(root, pid, "plan") == ap["sha256"] else "stale"


def verify(root, pid, st=None):
    """Compare recorded state against the filesystem. Files win over state."""
    st = st or load(root, pid)
    changes = []
    for key, rec in st["artifacts"].items():
        cur = file_hash(root, pid, key)
        old = rec.get("sha256")
        if old is None and cur is None:
            continue
        if old is None:
            changes.append({"artifact": key, "kind": "new_untracked", "detail": "exists but not recorded"})
        elif cur is None:
            changes.append({"artifact": key, "kind": "missing", "detail": "recorded but file missing"})
        elif cur != old:
            changes.append({"artifact": key, "kind": "modified_externally",
                            "detail": "content differs from last recorded version"})
    ma = markdown_approval_status(root, pid, st)
    if ma == "stale":
        changes.append({"artifact": "draft", "kind": "approval_stale",
                        "detail": "draft or figures changed after Markdown approval; re-approval required"})
        changes.extend(figure_changes(root, pid, st))
    pa = plan_approval_status(root, pid, st)
    if pa == "stale":
        changes.append({"artifact": "plan", "kind": "plan_approval_stale",
                        "detail": "plan changed after approval; re-approval required"})
    if IDX[st["stage"]] >= IDX["MARKDOWN_APPROVED"] and ma != "current":
        changes.append({"artifact": "draft", "kind": "stage_inconsistent",
                        "detail": "stage %s requires a current Markdown approval" % st["stage"]})
    if IDX[st["stage"]] >= IDX["PLAN_APPROVED"] and pa != "current":
        changes.append({"artifact": "plan", "kind": "stage_inconsistent",
                        "detail": "stage %s requires a current plan approval" % st["stage"]})
    ap = st.get("markdown_approval")
    if ap and not os.path.isfile(os.path.join(pdir(root, pid), ap["snapshot"])):
        changes.append({"artifact": "approved", "kind": "missing", "detail": "approved snapshot file missing"})
    elif ap and sha256_file(os.path.join(pdir(root, pid), ap["snapshot"])) != ap["sha256"]:
        changes.append({"artifact": "approved", "kind": "modified_externally",
                        "detail": "approved snapshot was altered; it must never be edited"})
    return changes


def sync(root, pid, st):
    """Accept the current file contents as the new recorded baseline (bumps versions)."""
    bumped = []
    for key, rec in st["artifacts"].items():
        cur = file_hash(root, pid, key)
        if cur != rec.get("sha256"):
            if cur is not None:
                rec["version"] = rec.get("version", 0) + 1
                bumped.append(key)
            rec["sha256"] = cur
    return bumped


def set_stage(root, pid, st, new, note=""):
    if new not in IDX:
        raise StateError("Unknown stage %r. Valid: %s" % (new, ", ".join(STAGES)))
    cur = st["stage"]
    if new == cur:
        return
    if new == "PLAN_APPROVED" and plan_approval_status(root, pid, st) != "current":
        raise StateError("PLAN_APPROVED can only be entered via 'approve-plan'")
    if new == "MARKDOWN_APPROVED" and markdown_approval_status(root, pid, st) != "current":
        raise StateError("MARKDOWN_APPROVED can only be entered via 'approve-markdown'")
    if IDX[new] >= IDX["LATEX_GENERATION"] and markdown_approval_status(root, pid, st) != "current":
        raise StateError("Cannot enter %s: no current Markdown approval (draft changed or never approved)" % new)
    if IDX[new] >= IDX["EVIDENCE_ANALYSIS"] and plan_approval_status(root, pid, st) != "current":
        raise StateError("Cannot enter %s: plan is not currently approved" % new)
    if IDX[new] > IDX[cur] + 1:
        raise StateError("Cannot skip stages: %s -> %s (next allowed: %s)" % (cur, new, STAGES[IDX[cur] + 1]))
    if IDX[new] > IDX[cur]:
        for s in STAGES[IDX[cur]:IDX[new]]:
            if s not in st["completed_stages"]:
                st["completed_stages"].append(s)
    else:  # rework: later stages are no longer complete
        st["completed_stages"] = [s for s in st["completed_stages"] if IDX[s] < IDX[new]]
    st["history"].append({"at": now(), "from": cur, "to": new, "note": note})
    st["stage"] = new


def pending_approvals(root, pid, st):
    out = []
    if st["stage"] == "PLAN_PENDING_APPROVAL":
        out.append("plan (say: %s)" % APPROVAL_PHRASES["plan"])
    if st["stage"] == "MARKDOWN_PENDING_APPROVAL" or (
            IDX[st["stage"]] >= IDX["MARKDOWN_PENDING_APPROVAL"] and markdown_approval_status(root, pid, st) != "current"):
        out.append("markdown (say: %s)" % APPROVAL_PHRASES["markdown"])
    return out


def backup(root, pid, relpath):
    """Copy a project file into .history/ before it is modified. Returns the backup path."""
    src = os.path.join(pdir(root, pid), relpath)
    if not os.path.isfile(src):
        raise StateError("Nothing to back up: %s" % relpath)
    stamp = now().replace(":", "").replace("-", "")
    name = "%s.%s.%s" % (os.path.basename(relpath), stamp, sha256_file(src)[:8])
    dst = os.path.join(pdir(root, pid), WORK, "history", name)
    shutil.copy2(src, dst)
    return os.path.relpath(dst, pdir(root, pid))


def approve(root, pid, st, kind, phrase):
    if phrase != APPROVAL_PHRASES[kind]:
        raise StateError("Approval refused: phrase must be exactly %r (got %r)." % (APPROVAL_PHRASES[kind], phrase))
    d = pdir(root, pid)
    if kind == "plan":
        if st["stage"] != "PLAN_PENDING_APPROVAL":
            raise StateError("Plan approval requires stage PLAN_PENDING_APPROVAL (now %s)" % st["stage"])
        if not os.path.isfile(artifact_path(root, pid, "plan")):
            raise StateError("plan.md does not exist")
        sync(root, pid, st)
        h = file_hash(root, pid, "plan")
        st["plan_approval"] = {"approved_at": now(), "sha256": h, "version": st["artifacts"]["plan"]["version"]}
        set_stage(root, pid, st, "PLAN_APPROVED", "plan approved")
        return st
    # markdown
    if st["stage"] != "MARKDOWN_PENDING_APPROVAL":
        raise StateError("Markdown approval requires stage MARKDOWN_PENDING_APPROVAL (now %s)" % st["stage"])
    draft = artifact_path(root, pid, "draft")
    if not os.path.isfile(draft):
        raise StateError("%s-report.md does not exist" % pid)
    h = sha256_file(draft)
    lv = st.get("last_validation")
    if not lv or lv.get("sha256") != h:
        raise StateError("Draft has no validation for its current content. Run validate_markdown.py first.")
    if lv.get("errors", 1) > 0:
        raise StateError("Last validation has %d error(s); fix them before approval." % lv["errors"])
    sync(root, pid, st)
    ver = st["artifacts"]["draft"]["version"]
    snap_rel = os.path.join(WORK, "approved", "draft-approved-v%d.md" % ver)
    snap = os.path.join(d, snap_rel)
    if os.path.exists(snap):
        raise StateError("Refusing to overwrite existing approved snapshot %s" % snap_rel)
    os.makedirs(os.path.dirname(snap), exist_ok=True)
    shutil.copy2(draft, snap)
    os.chmod(snap, 0o444)
    st["markdown_approval"] = {"approved_at": now(), "sha256": h, "version": ver, "snapshot": snap_rel,
                               "figures": figure_dependencies(root, pid)}
    set_stage(root, pid, st, "MARKDOWN_APPROVED", "markdown approved")
    return st


def publish(root, pid, st):
    """Copy the final <id>.tex and <id>.pdf from .ms/latex/ to the visible project folder."""
    d = pdir(root, pid)
    out = []
    for ext in ("tex", "pdf"):
        src = os.path.join(d, WORK, "latex", "%s.%s" % (pid, ext))
        if not os.path.isfile(src):
            raise StateError("Cannot publish: %s missing (generate and compile first)" % os.path.relpath(src, d))
        shutil.copy2(src, os.path.join(d, "%s.%s" % (pid, ext)))
        out.append("%s.%s" % (pid, ext))
    return out


def summary(root, pid, st, changes):
    return {
        "project_id": pid,
        "doctype": st["doctype"],
        "title": st.get("title"),
        "stage": st["stage"],
        "next_stage": STAGES[IDX[st["stage"]] + 1] if st["stage"] != "COMPLETED" else None,
        "completed_stages": st["completed_stages"],
        "pending_approvals": pending_approvals(root, pid, st),
        "markdown_approval": markdown_approval_status(root, pid, st),
        "plan_approval": plan_approval_status(root, pid, st),
        "approved_markdown": (st.get("markdown_approval") or {}).get("snapshot"),
        "draft_version": st["artifacts"]["draft"]["version"],
        "last_validation": st.get("last_validation"),
        "outstanding_issues": st["outstanding_issues"],
        "drift": changes,
        "updated_at": st["updated_at"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.getcwd(), help="repository root (default: cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("project"); p.add_argument("--doctype", required=True); p.add_argument("--title")
    sub.add_parser("list")
    sub.add_parser("doctypes", help="list available document types")
    for name in ("status", "verify", "sync"):
        p = sub.add_parser(name); p.add_argument("project", nargs="?")
        if name == "status":
            p.add_argument("--brief", action="store_true")
        if name == "verify":
            p.add_argument("--fix", action="store_true", help="demote stage if approval is stale")
    p = sub.add_parser("stage"); p.add_argument("project", nargs="?"); p.add_argument("stage"); p.add_argument("--note", default="")
    p = sub.add_parser("backup"); p.add_argument("project", nargs="?"); p.add_argument("file")
    p = sub.add_parser("approve-plan"); p.add_argument("project", nargs="?"); p.add_argument("--phrase", required=True)
    p = sub.add_parser("approve-markdown"); p.add_argument("project", nargs="?"); p.add_argument("--phrase", required=True)
    p = sub.add_parser("publish", help="copy final .tex/.pdf from .ms/latex to the visible project folder"); p.add_argument("project", nargs="?")
    p = sub.add_parser("path"); p.add_argument("project", nargs="?"); p.add_argument("what", choices=list(ARTIFACTS) + ["dir"])
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)

    try:
        if a.cmd == "init":
            st = init_project(root, a.project, a.doctype, a.title)
            print("Initialised %s (doctype %s) at %s" % (a.project, a.doctype, pdir(root, a.project)))
            return 0
        if a.cmd == "doctypes":
            dd = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "doctypes")
            for fn in sorted(os.listdir(dd)):
                if fn.endswith(".yaml"):
                    y = load_yaml(os.path.join(dd, fn))
                    print("%s\t%s\trequired: %s" % (y.get("name"), y.get("description"), ", ".join(y.get("required_sections") or [])))
            return 0
        if a.cmd == "list":
            for p_ in list_projects(root):
                s = load(root, p_)
                print("%s\t%s\t%s" % (p_, s["doctype"], s["stage"]))
            return 0
        pid = resolve(root, a.project)
        st = load(root, pid)
        if a.cmd == "path":
            print(pdir(root, pid) if a.what == "dir" else artifact_path(root, pid, a.what))
            return 0
        if a.cmd == "status":
            ch = verify(root, pid, st)
            s = summary(root, pid, st, ch)
            if a.brief:
                print("ManuScript project %s [%s] stage=%s next=%s pending=%s drift=%d" % (
                    pid, st["doctype"], s["stage"], s["next_stage"], s["pending_approvals"] or "none", len(ch)))
            else:
                print(json.dumps(s, indent=2))
            return 0
        if a.cmd == "verify":
            ch = verify(root, pid, st)
            if a.fix and any(c["kind"] in ("approval_stale", "stage_inconsistent") and c["artifact"] == "draft" for c in ch):
                if IDX[st["stage"]] >= IDX["MARKDOWN_APPROVED"]:
                    set_stage(root, pid, st, "MARKDOWN_PENDING_APPROVAL", "draft changed after approval")
                    save(root, pid, st)
                    ch = verify(root, pid, st)
            print(json.dumps({"project": pid, "stage": st["stage"], "consistent": not ch, "changes": ch}, indent=2))
            return 0 if not ch else 3
        if a.cmd == "sync":
            b = sync(root, pid, st)
            save(root, pid, st)
            print(json.dumps({"updated": b}))
            return 0
        if a.cmd == "stage":
            set_stage(root, pid, st, a.stage, a.note)
            save(root, pid, st)
            print("%s -> %s" % (pid, st["stage"]))
            return 0
        if a.cmd == "publish":
            if st["stage"] not in ("PDF_QA", "COMPLETED"):
                raise StateError("publish requires stage PDF_QA or COMPLETED (now %s)" % st["stage"])
            print("published: " + ", ".join(publish(root, pid, st)))
            return 0
        if a.cmd == "backup":
            print(backup(root, pid, a.file))
            return 0
        if a.cmd in ("approve-plan", "approve-markdown"):
            approve(root, pid, st, "plan" if a.cmd == "approve-plan" else "markdown", a.phrase)
            save(root, pid, st)
            print("%s approved; stage=%s" % (a.cmd.split("-")[1], st["stage"]))
            return 0
    except StateError as e:
        print("ERROR: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
