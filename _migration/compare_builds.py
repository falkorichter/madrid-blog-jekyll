#!/usr/bin/env python3
"""
Build the site twice — from a git revision and from the working tree — and compare the output.
Used to prove that a change (e.g. HTML -> Markdown posts) does not change what readers see.

  python3 _migration/compare_builds.py [REV]      (default REV: HEAD)

Reports: files only in one build; single posts/pages whose content renders differently (the
content area, compared as normalized HTML: whitespace, entities and attribute order don't
count); other pages (home, archives, …) that differ apart from <meta name="description">.
Exit code 1 if the content of any post/page differs.
Needs `jekyll` on PATH (with rbenv: RBENV_VERSION=3.1.2).
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from html2md import equivalent  # noqa: E402

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY = re.compile(r'<div class="(?:entry-content|storycontent)">(.*?)'
                  r'(?:<div class="(?:clear|feedback)"|</div>\s*</div>)', re.S)


def build(src, dest):
    env = dict(os.environ, RBENV_VERSION=os.environ.get("RBENV_VERSION", "3.1.2"), JEKYLL_ENV="production")
    subprocess.run(["jekyll", "build", "-q", "-s", src, "-d", dest], check=True, env=env)


def files(root):
    return {os.path.relpath(f, root) for f in glob.glob(os.path.join(root, "**", "*"), recursive=True)
            if os.path.isfile(f)}


def main(rev="HEAD"):
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src")
        os.makedirs(src)
        archive = subprocess.run(["git", "-C", SITE, "archive", rev], check=True, capture_output=True).stdout
        subprocess.run(["tar", "-x", "-C", src], input=archive, check=True)
        before, after = os.path.join(tmp, "before"), os.path.join(tmp, "after")
        build(src, before)
        build(SITE, after)

        fa, fb = files(before), files(after)
        body_diff, page_diff = [], []
        for rel in sorted(fa & fb):
            if not rel.endswith(".html"):
                continue
            a = open(os.path.join(before, rel), encoding="utf-8").read()
            b = open(os.path.join(after, rel), encoding="utf-8").read()
            if a == b:
                continue
            ba, bb = BODY.findall(a), BODY.findall(b)
            # list pages (home, paging, category/tag archives) only hold teasers
            is_list = rel == "index.html" or rel.split("/")[0] in ("page", "category", "tag", "archiv")
            if not is_list and ba and bb and not equivalent(ba[0], bb[0]):
                body_diff.append(rel)
                continue
            strip = lambda h: re.sub(r'<meta name="description"[^>]*>', "", h)  # noqa: E731
            if not equivalent(strip(a), strip(b)):
                page_diff.append(rel)

    print(f"{rev} vs working tree: {len(fa)} / {len(fb)} files")
    for label, items in (("only in " + rev, sorted(fa - fb)), ("only in working tree", sorted(fb - fa)),
                         ("content differs", body_diff), ("other page differences", page_diff)):
        print(f"  {label}: {len(items)}" + "".join(f"\n    {i}" for i in items[:20]))
    return 1 if body_diff else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
