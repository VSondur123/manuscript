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
