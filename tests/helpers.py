import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
FIXTURES = os.path.join(ROOT, "tests", "fixtures")
DOCTYPES = os.path.join(ROOT, "doctypes")


def copy_valid_project():
    """Copy the valid fixture into a fresh temp dir; returns the path."""
    d = tempfile.mkdtemp(prefix="ms_test_")
    dst = os.path.join(d, "proj")
    shutil.copytree(os.path.join(FIXTURES, "valid_project"), dst)
    return dst


def codes(res, kind):
    return [i["code"] for i in res[kind]]


def install_fixture(d, pid):
    """Copy the valid fixture into project dir d using the real layout: plan.md + <pid>-report.md visible, rest in .ms/."""
    src = os.path.join(FIXTURES, "valid_project")
    shutil.copy(os.path.join(src, "plan.md"), os.path.join(d, "plan.md"))
    with open(os.path.join(src, "draft.md"), encoding="utf-8") as f:
        text = f.read().replace("](figures/", "](.ms/figures/")
    with open(os.path.join(d, "%s-report.md" % pid), "w", encoding="utf-8") as f:
        f.write(text)
    shutil.copy(os.path.join(src, "refs.bib"), os.path.join(d, ".ms", "references.bib"))
    shutil.copytree(os.path.join(src, "figures"), os.path.join(d, ".ms", "figures"), dirs_exist_ok=True)


def run_script(*args, cwd):
    """Run a script from scripts/; returns (returncode, stdout+stderr)."""
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", args[0])] + list(args[1:]), cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def approved_project(config_extra="", doctype="research-report", pid="demo", approve=True, config_after=""):
    """Fresh temp workspace with the fixture installed and (optionally) plan+Markdown approved through the REAL
    state engine using the test-harness approval phrases. `config_extra` is appended to project-config.yaml
    (e.g. 'citation_style: apa7' or 'layout:\\n  paper: letter'). `doctype` is switched in state AFTER approval, because
    the fixture only satisfies research-report's required sections. `config_after` is appended after approval. Returns (root, project_dir)."""
    import json
    root = tempfile.mkdtemp(prefix="ms_proj_")
    run_script("ms_state.py", "init", pid, "--doctype", "research-report", cwd=root)
    d = os.path.join(root, "manuscript", pid)
    install_fixture(d, pid)
    if config_extra:
        with open(os.path.join(d, ".ms", "project-config.yaml"), "a", encoding="utf-8") as f:
            f.write("\n" + config_extra + "\n")
    if approve:
        for s in ["DISCOVERY_IN_PROGRESS", "DISCOVERY_COMPLETE", "PLAN_PENDING_APPROVAL"]:
            run_script("ms_state.py", "stage", s, cwd=root)
        run_script("ms_state.py", "approve-plan", "--phrase", "APPROVE PLAN", cwd=root)
        for s in ["EVIDENCE_ANALYSIS", "MARKDOWN_DRAFTING", "MARKDOWN_VALIDATION", "MARKDOWN_PENDING_APPROVAL"]:
            run_script("ms_state.py", "stage", s, cwd=root)
        run_script("validate_markdown.py", cwd=root)
        rc, out = run_script("ms_state.py", "approve-markdown", "--phrase", "APPROVE MARKDOWN", cwd=root)
        assert rc == 0, out
    if config_after:  # appended after approval (e.g. invalid values that validate_markdown would block at approval time)
        with open(os.path.join(d, ".ms", "project-config.yaml"), "a", encoding="utf-8") as f:
            f.write("\n" + config_after + "\n")
    if doctype != "research-report":
        p = os.path.join(d, ".ms", "state.json")
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        st["doctype"] = doctype
        with open(p, "w", encoding="utf-8") as f:
            json.dump(st, f)
    return root, d
