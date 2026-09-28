#!/usr/bin/env python3
"""
Export the Falko en Madrid blog from the local WordPress (docker compose service `madrid`,
http://localhost:8090) into this Jekyll site.

Source: the WordPress REST API (`?rest_route=`, pretty /wp-json/ is not routed there). Its
`content.rendered` is what WordPress shows: [gallery=N] already rendered as thumbnail grids by
madrid-local/wp-content/mu-plugins/madrid.php, old madrid.falkorichter.de links rewritten.

Writes (and replaces on every run):
  _posts/YYYY-MM-DD-<slug>.html       the published posts
  _pages/<slug>.html                  the pages (without Newsletter; Impressum only if it has
                                      more than the old Google Analytics notice)
  assets/galleries/<gallery>/…        NextGEN gallery photos (+ thumbs/)
  assets/images/YYYY/MM/…, assets/files/YYYY/MM/…   other referenced uploads
  _data/{categories,tags,blogroll,comments,moved_files}.json
  _migration/export-report.json

Read-only towards WordPress and the DB. Usage (from the madrid-site/ folder):
  python3 _migration/export_rest.py
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from html.parser import HTMLParser
from urllib.parse import quote, unquote

WP = os.environ.get("WP_URL", "http://localhost:8090")
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = os.path.dirname(SITE)
# Where referenced files are copied from, in order. madrid-local/ is the content-checked copy.
FILE_SOURCES = [os.path.join(PROJECT, "madrid-local"), os.path.join(PROJECT, "ftp-madrid")]
# Only passive file types are copied (never php/html/js/swf/svg from the compromised host).
COPY_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".pdf", ".rtf", ".txt"}
SKIP_PAGES = {"newsletter"}  # Subscribe2 sign-up form, plugin is gone
DB_CONTAINER, DB_NAME, DB_PREFIX = "vf_db", "madrid", "madrid_"
MORE = "<!--more-->"


def get_all(endpoint, fields=None, extra=""):
    items, page = [], 1
    while True:
        url = f"{WP}/?rest_route=/wp/v2/{endpoint}&per_page=100&page={page}{extra}"
        if fields:
            url += "&_fields=" + ",".join(fields)
        with urllib.request.urlopen(url, timeout=120) as r:
            items += json.load(r)
            if page >= int(r.headers.get("X-WP-TotalPages", 1)):
                return items
        page += 1


# --- content cleanup ------------------------------------------------------------

def embed_iframe(m):
    """Flash <object>/<embed> video players -> iframes (YouTube, Vimeo); keeps the size."""
    obj = m.group(0)
    w = re.search(r'width="(\d+)"', obj)
    h = re.search(r'height="(\d+)"', obj)
    size = f' width="{w.group(1) if w else 425}" height="{h.group(1) if h else 344}"'
    yt = re.search(r"youtube\.com/v/([\w-]{11})", obj)
    vimeo = re.search(r"clip_id=(\d+)", obj)
    if yt:
        src = f"https://www.youtube-nocookie.com/embed/{yt.group(1)}"
    elif vimeo:
        src = f"https://player.vimeo.com/video/{vimeo.group(1)}"
    else:
        return obj
    return f'<iframe{size} src="{src}" frameborder="0" loading="lazy" allowfullscreen></iframe>'


def clean(body):
    # Local WordPress URL (and the old domain, should already be rewritten) -> site-relative.
    body = re.sub(r"https?://(?:localhost:8090|madrid\.falkorichter\.de)(?=/)", "", body)
    body = re.sub(r"https?://(?:localhost:8090|madrid\.falkorichter\.de)\b", "/", body)
    # Links written without a scheme ("www.flickr.com/…") resolve as paths on this site.
    body = re.sub(r"""(href=["'])(www\.)""", r"\1http://\2", body)
    # Flash video players -> iframes.
    body = re.sub(r"<object.*?</object>", embed_iframe, body, flags=re.S)
    body = re.sub(r"<embed[^>]*youtube\.com/v/[^>]*>(?:</embed>)?", embed_iframe, body)
    # Responsive-image variants WordPress adds on output: the column is ~485px wide anyway and
    # the lightbox opens the original, so keep src only (no extra size variants to copy).
    body = re.sub(r"""\s(?:srcset|sizes)=(["']).*?\1""", "", body)
    # Embedded maps/tracks over https (mixed content is blocked on an https site).
    body = re.sub(r'(<iframe[^>]*src=")http://', r"\1https://", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip() + "\n"


# --- <!--more--> ------------------------------------------------------------------
# WordPress keeps the author's <!--more--> comment in the rendered HTML, but after
# wpautop it often sits inside a paragraph ("…Satz.<!--more--></p>"). Jekyll cuts the
# home-page teaser at the marker, so the elements still open there are closed before
# the marker and reopened after it; the teaser stays balanced HTML.

def alnum_count(text):
    return sum(1 for ch in text if ch.isalnum())


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# Opening one of these implicitly closes an open <p> (HTML parsing rules).
CLOSES_P = {"address", "article", "aside", "blockquote", "div", "dl", "fieldset", "figure", "footer", "form",
            "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "ol", "p", "pre", "section", "table", "ul"}


class BlockEnds(HTMLParser):
    """Records (offset, alnum-so-far, open-tag stack) after every end tag."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.text = text
        self.lines = [0]
        for line in text.splitlines(keepends=True):
            self.lines.append(self.lines[-1] + len(line))
        self.stack, self.count, self.ends = [], 0, []
        self.feed(text)
        self.close()

    def _offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in CLOSES_P and self.stack and self.stack[-1][0] == "p":
            self.stack.pop()
        if tag == "li" and self.stack and self.stack[-1][0] == "li":
            self.stack.pop()
        if tag not in VOID:
            self.stack.append((tag, self.get_starttag_text()))

    def handle_endtag(self, tag):
        if tag in VOID or not any(t == tag for t, _ in self.stack):
            return
        while self.stack and self.stack.pop()[0] != tag:
            pass
        end = self.text.index(">", self._offset()) + 1
        self.ends.append((end, self.count, list(self.stack)))

    def handle_data(self, data):
        self.count += alnum_count(data)


def normalize_more(body):
    m = re.search(r"<!--more.*?-->", body)
    if not m:
        return body, False
    before, after = body[:m.start()], re.sub(r"<!--more.*?-->", "", body[m.end():])
    if not re.sub(r"<[^>]+>|\s|&nbsp;", "", after):
        return before + after, False  # nothing after the marker — no teaser needed
    open_at_marker = BlockEnds(before).stack
    # End tags right after the marker close reopened elements — don't reopen those at all.
    stack = list(open_at_marker)
    while True:
        m_end = re.match(r"\s*</([a-zA-Z0-9]+)\s*>", after)
        if not m_end or not any(t == m_end.group(1).lower() for t, _ in stack):
            break
        while stack.pop()[0] != m_end.group(1).lower():
            pass
        after = after[m_end.end():]
    close = "".join(f"</{t}>" for t, _ in reversed(open_at_marker))
    reopen = "".join(start for _, start in stack)
    body = before + close + "\n" + MORE + "\n" + reopen + after
    body = re.sub(r"<p>\s*</p>\s*", "", body)  # empty paragraphs left around the marker
    return body, True


# --- files ------------------------------------------------------------------------

def find_source(rel):
    """Locate a referenced file; tolerate case differences (old host was case-insensitive)."""
    for base in FILE_SOURCES:
        path = os.path.join(base, rel.lstrip("/"))
        encoded = os.path.join(os.path.dirname(path), quote(os.path.basename(path)))
        if not os.path.isfile(path) and os.path.isfile(encoded):
            return encoded  # some uploads were saved with a literal "%20" in the name
        if os.path.isfile(path):
            return path
        if "/uploads/" in path and not os.path.isfile(path):
            alt = path.replace("/wp-content/uploads/", "/wp-content/")  # old-style upload path
            if os.path.isfile(alt):
                return alt
        parent, name = os.path.split(path)
        if os.path.isdir(parent):
            for cand in os.listdir(parent):
                if cand.lower() == name.lower() and os.path.isfile(os.path.join(parent, cand)):
                    return os.path.join(parent, cand)
    return None


def yaml_str(s):
    return json.dumps(s, ensure_ascii=False)  # JSON strings are valid YAML scalars



IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
REF_RE = re.compile(r"""((?:src|href)=(["']))(/wp-content/[^"'#?]+)""")


def new_location(rel, first_used):
    """/wp-content/gallery/<g>/thumbs/thumbs_x.jpg -> /assets/galleries/<g>/thumbs/x.jpg
    /wp-content/gallery/<g>/x.jpg               -> /assets/galleries/<g>/x.jpg
    /wp-content/uploads/2008/10/x.jpg           -> /assets/images/2008/10/x.jpg
    Files without a year/month get the date of the first post using them."""
    name = re.sub(r"(?:%20|\s)+", "-", os.path.basename(rel))
    g = re.match(r"/wp-content/gallery/([^/]+)/(thumbs/)?", rel)
    if g:
        if g.group(2):
            return f"/assets/galleries/{g.group(1)}/thumbs/{re.sub(r'^thumbs_', '', name)}"
        return f"/assets/galleries/{g.group(1)}/{name}"
    kind = "images" if os.path.splitext(rel)[1].lower() in IMAGE_EXTS else "files"
    m = re.search(r"/(\d{4})/(\d{2})/", rel)
    year, month = m.groups() if m else (first_used[:4], first_used[5:7])
    return f"/assets/{kind}/{year}/{month}/{name}"


RESIZED_RE = re.compile(r"^(.+?)(?:-\d+x\d+|\.thumbnail)(\.\w+)$")  # foo-480x336.png, foo.thumbnail.jpg


def original_of(path):
    """Full-size file for a WordPress preview: foo-480x336.png, foo.thumbnail.jpg,
    wpid-thumb-1431.jpg (WordPress for Android) -> foo.png, foo.jpg, wpid-1431.jpg."""
    candidates = []
    r = RESIZED_RE.match(path)
    if r:
        candidates.append(r.group(1) + r.group(2))
    base = candidates[0] if candidates else path
    if "/wpid-thumb-" in base:
        candidates.insert(0, base.replace("/wpid-thumb-", "/wpid-"))
    return next((c for c in candidates if find_source(c)), None)
IMG_RE = re.compile(r"""<img[^>]*\ssrc=["'](/wp-content/[^"']+)["'][^>]*>""")


def link_previews(body):
    """Wrap unlinked resized previews in a link to the original, so the lightbox can open it."""
    def wrap(m):
        start = m.start()
        if body.rfind("<a ", 0, start) > body.rfind("</a>", 0, start):
            return m.group(0)  # already inside a link
        original = original_of(unquote(m.group(1)))
        if not original:
            return m.group(0)
        return f'<a href="{quote(original)}">{m.group(0)}</a>'
    return IMG_RE.sub(wrap, body)



def fix_mojibake(s):
    try:
        return s.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def blogroll():
    """Blogroll (Links widget) from the DB — the REST API does not expose it."""
    sql = (f"select json_object('name', link_name, 'url', link_url) from {DB_PREFIX}links "
           "where link_visible='Y' order by link_name")
    out = subprocess.run(["docker", "exec", DB_CONTAINER, "mariadb", "-uroot", "-proot", DB_NAME,
                          "--default-character-set=utf8mb4", "-N", "-r", "-e", sql],
                         capture_output=True, text=True, check=True).stdout
    links = [json.loads(line) for line in out.splitlines() if line.strip()]
    return [{"name": fix_mojibake(l["name"]), "url": l["url"]} for l in links]


def db_terms():
    """post ID -> {"category": [...], "post_tag": [...]} straight from the DB.
    The REST API can't be trusted here: this 2008 DB has "shared terms" (term_id 1 is both the
    category "Blog" and a tag "Blog"), and current WordPress reports that category as a tag."""
    sql = ("select json_object('post', r.object_id, 'tax', tt.taxonomy, 'name', t.name, 'slug', t.slug) "
           f"from {DB_PREFIX}term_relationships r "
           f"join {DB_PREFIX}term_taxonomy tt on tt.term_taxonomy_id = r.term_taxonomy_id "
           f"join {DB_PREFIX}terms t on t.term_id = tt.term_id "
           "where tt.taxonomy in ('category', 'post_tag') order by t.name")
    out = subprocess.run(["docker", "exec", DB_CONTAINER, "mariadb", "-uroot", "-proot", DB_NAME,
                          "--default-character-set=utf8mb4", "-N", "-r", "-e", sql],
                         capture_output=True, text=True, check=True).stdout
    terms = {}
    for line in out.splitlines():
        if line.strip():
            row = json.loads(line)
            name = html.unescape(fix_mojibake(row["name"]))
            terms.setdefault(row["post"], {"category": [], "post_tag": []})[row["tax"]].append((name, row["slug"]))
    return terms


def write_json(name, data):
    with open(os.path.join(SITE, "_data", name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def front_matter(fields):
    return "---\n" + "".join(f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in fields.items()) + "---\n"


def main():
    posts = get_all("posts")
    pages = get_all("pages")
    terms = db_terms()
    users = {u["id"]: u["name"] for u in get_all("users", ["id", "name"])}
    comments = get_all("comments", extra="&order=asc")
    # WordPress attachment pages (/<post>/<image>/) -> the image file itself
    attachments = {re.sub(r"^https?://[^/]+", "", a["link"]): clean(a["source_url"]).strip()
                   for a in get_all("media", ["link", "source_url"])}

    for d in ("_posts", "_pages"):
        for name in os.listdir(os.path.join(SITE, d)):
            if name.endswith((".html", ".md")):
                os.remove(os.path.join(SITE, d, name))
    for d in ("assets/galleries", "assets/files"):
        shutil.rmtree(os.path.join(SITE, d), ignore_errors=True)
    for year_dir in os.listdir(os.path.join(SITE, "assets", "images")):
        if re.fullmatch(r"\d{4}", year_dir):  # previous run's output; theme/ stays
            shutil.rmtree(os.path.join(SITE, "assets", "images", year_dir))

    report = {"posts": 0, "pages": 0, "skipped_pages": [], "teasers": 0, "comments": 0,
              "missing_files": {}, "skipped_file_types": {}, "copied_files": 0}

    # Pass 1: clean the bodies, collect referenced files (with the date of the first post using them).
    entries, refs = [], {}
    for p in sorted(posts, key=lambda p: p["date_gmt"]) + pages:
        if p["type"] == "page":
            text = re.sub(r"<[^>]+>|\s", "", p["content"]["rendered"])
            if p["slug"] in SKIP_PAGES or (p["slug"] == "impressum" and "GoogleAnalytics" in text
                                           and len(text) < 2500):
                report["skipped_pages"].append(p["slug"])
                continue
        body = clean(p["content"]["rendered"])
        body, has_teaser = normalize_more(body)
        report["teasers"] += has_teaser
        body = re.sub(r"""(href=["'])(/[^"'#?]+/)(?=["'])""",
                      lambda m: m.group(1) + attachments.get(m.group(2), m.group(2)), body)
        body = link_previews(body)
        for m in REF_RE.finditer(body):
            refs.setdefault(unquote(m.group(3)), {"first_used": p["date"], "used_by": set()})["used_by"].add(p["slug"])
        entries.append((p, body))

    # Pass 2: copy files into assets/ and remember old -> new.
    moved, taken = {}, {}
    for rel, info in sorted(refs.items()):
        used_by = sorted(info["used_by"])
        if os.path.splitext(rel)[1].lower() not in COPY_EXTS:
            report["skipped_file_types"][rel] = used_by
            continue
        src = find_source(rel)
        if not src:
            report["missing_files"][rel] = used_by
            continue
        new = new_location(rel, info["first_used"])
        stem, ext = os.path.splitext(new)
        n = 2
        while taken.get(new.lower(), src) != src:  # same name, different file -> suffix
            new, n = f"{stem}-{n}{ext}", n + 1
        taken[new.lower()] = src
        dest = os.path.join(SITE, new.lstrip("/"))
        if not os.path.exists(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            report["copied_files"] += 1
        moved[rel] = new

    # Pass 3: rewrite links and write posts + pages.
    def relink(m):
        new = moved.get(unquote(m.group(3)))
        return m.group(1) + quote(new) if new else m.group(0)

    dead_img = re.compile(r"""<img[^>]*\ssrc=["']/wp-content/[^>]*>""")
    dead_link = re.compile(r"""<a[^>]*\shref=["']/(?:wp-content/|wp-admin/|wp-login\.php)[^>]*>(.*?)</a>""", re.S)
    # Links to pages that are not exported (Newsletter, GA-only Impressum): keep the text.
    skipped = "|".join(re.escape(s) for s in report["skipped_pages"]) or "(?!)"
    dead_page = re.compile(r"""<a[^>]*\shref=["']/(?:%s)/?["'][^>]*>(.*?)</a>""" % skipped, re.S)
    report["dead_links_unwrapped"] = report["dead_images_removed"] = 0
    used_cats, used_tags = {}, {}
    for p, body in entries:
        body = REF_RE.sub(relink, body)
        body, n = dead_img.subn("", body)
        report["dead_images_removed"] += n
        body, n = dead_link.subn(r"\1", body)
        report["dead_links_unwrapped"] += n
        body, n = dead_page.subn(r"\1", body)
        report["dead_links_unwrapped"] += n
        permalink = re.sub(r"^https?://[^/]+", "", p["link"])
        title = html.unescape(p["title"]["rendered"])
        if p["type"] == "page":
            fields = {"title": title, "permalink": permalink, "nav": True, "wp_id": p["id"]}
            path = os.path.join(SITE, "_pages", f"{p['slug']}.html")
            report["pages"] += 1
        else:
            t = terms.get(p["id"], {"category": [], "post_tag": []})
            categories = [name for name, _ in t["category"]]
            post_tags = [name for name, _ in t["post_tag"]]
            used_cats.update(t["category"])
            used_tags.update(t["post_tag"])
            fields = {"title": title, "date": p["date_gmt"].replace("T", " ") + " +0000",
                      "permalink": permalink, "author": users.get(p["author"], ""),
                      "categories": categories, "tags": post_tags, "wp_id": p["id"]}
            path = os.path.join(SITE, "_posts", f"{p['date'][:10]}-{p['slug']}.html")
            report["posts"] += 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(front_matter(fields) + body)

    # Sidebar/taxonomy data: display name -> original slug (keeps /category|tag/<slug>/ URLs).
    write_json("categories.json", [{"name": n, "slug": s} for n, s in sorted(used_cats.items(), key=lambda c: c[0].lower())])
    write_json("tags.json", [{"name": n, "slug": s} for n, s in sorted(used_tags.items(), key=lambda t: t[0].lower())])
    write_json("blogroll.json", blogroll())

    # Old comments, shown read-only under the posts.
    post_by_id = {p["id"]: p for p in posts}
    data = []
    for c in comments:
        p = post_by_id.get(c["post"])
        if not p or c["status"] != "approved":
            continue
        data.append({"id": c["id"], "url": re.sub(r"^https?://[^/]+", "", p["link"]),
                     "post_title": html.unescape(p["title"]["rendered"]),
                     "author": html.unescape(c["author_name"]), "author_url": c.get("author_url") or "",
                     "date": c["date"].replace("T", " "), "content": clean(c["content"]["rendered"]).strip()})
    write_json("comments.json", data)
    report["comments"] = len(data)

    write_json("moved_files.json", [{"from": old, "to": new} for old, new in sorted(moved.items())])

    with open(os.path.join(SITE, "_migration", "export-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"posts: {report['posts']}  pages: {report['pages']} (skipped {report['skipped_pages']})  "
          f"teasers: {report['teasers']}  comments: {report['comments']}  files: {report['copied_files']} copied, "
          f"{len(moved)} links moved, {len(report['missing_files'])} missing, "
          f"{len(report['skipped_file_types'])} skipped (type)")


if __name__ == "__main__":
    sys.exit(main())
