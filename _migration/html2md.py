"""
Conservative HTML -> Markdown (kramdown) conversion for exported WordPress posts.

Only a small, safe subset of HTML is converted: paragraphs, line breaks, links, emphasis,
inline code, headings, lists, block quotes, horizontal rules and images (size/alignment are
kept as kramdown attribute lists, e.g. ![alt](src){: .alignleft width="300"}). Anything else
(iframes, divs, spans, tables, inline styles, …) makes convert() return None: the post stays HTML.

A conversion is only accepted when the Markdown renders back to the *same* HTML with Jekyll's
own kramdown settings (see kramdown_render.rb and equivalent()); otherwise the post stays HTML.
"""
import html
import json
import os
import re
import subprocess
from html.parser import HTMLParser

MORE = "<!--more-->"
VOID = {"br", "img", "hr"}
BLOCK = {"p", "ul", "ol", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "hr"}
INLINE = {"a", "strong", "b", "em", "i", "code", "br", "img"}
# Attributes that are dropped: no effect in these themes (WordPress output defaults).
IGNORED_ATTRS = {"loading", "decoding"}
IGNORED_CLASSES = {"wp-block-paragraph"}
ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "rel"},
    "img": {"src", "alt", "title", "width", "height", "class", "align"},
    "p": {"class"},  # only the ignored WordPress default class, see _attrs()
}


class Unsupported(Exception):
    pass


class Node:
    def __init__(self, tag, attrs=None, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs or {}), parent, []


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        if tag not in BLOCK | INLINE:
            raise Unsupported(tag)
        # HTML's implied end of <p> / <li>
        if tag in BLOCK and self.cur.tag == "p":
            self.cur = self.cur.parent
        if tag == "li" and self.cur.tag == "li":
            self.cur = self.cur.parent
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            raise Unsupported(tag)
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is self.root:
            raise Unsupported(f"stray </{tag}>")
        self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)

    def handle_comment(self, data):
        if f"<!--{data}-->" != MORE:
            raise Unsupported("comment")
        self.cur.children.append(Node("#more", parent=self.cur))


def _attrs(node):
    attrs = {k: v for k, v in node.attrs.items() if k not in IGNORED_ATTRS}
    allowed = ALLOWED_ATTRS.get(node.tag, set())
    if node.tag == "p":
        classes = set((attrs.pop("class", "") or "").split()) - IGNORED_CLASSES
        if classes or attrs:
            raise Unsupported("p attributes")
        return {}
    for k in attrs:
        if k not in allowed:
            raise Unsupported(f"{node.tag}.{k}")
    return attrs


def _ial(attrs, skip=()):
    parts = []
    for k, v in attrs.items():
        if k in skip:
            continue
        if k == "class":
            parts += ["." + c for c in (v or "").split()]
        else:
            if '"' in (v or "") or "}" in (v or ""):
                raise Unsupported("attribute quoting")
            parts.append(f'{k}="{v}"')
    return "{: " + " ".join(parts) + "}" if parts else ""


def _escape(text):
    text = re.sub(r"([\\`*_\[\]{}<>|#!$\"'])", r"\\\1", text)
    text = text.replace("--", "-\\-").replace("...", "\\...")  # kramdown typographic symbols
    return text


def _url(u):
    if re.search(r"[\s()<>]", u):
        if "<" in u or ">" in u:
            raise Unsupported("url")
        return f"<{u}>"
    return u


def _inline(nodes):
    out = []
    for n in nodes:
        if isinstance(n, str):
            out.append(_escape(re.sub(r"\s+", " ", n)))  # newlines in HTML text are just spaces
            continue
        if n.tag in BLOCK or n.tag == "#more":
            raise Unsupported(f"block <{n.tag}> inside inline content")
        attrs = _attrs(n)
        if n.tag == "br":
            out.append("  \n")
        elif n.tag in ("strong", "b"):
            inner = _inline(n.children)
            if not inner.strip() or inner != inner.strip():
                raise Unsupported("emphasis whitespace")
            out.append(f"**{inner}**")
        elif n.tag in ("em", "i"):
            inner = _inline(n.children)
            if not inner.strip() or inner != inner.strip():
                raise Unsupported("emphasis whitespace")
            out.append(f"*{inner}*")
        elif n.tag == "code":
            text = "".join(c for c in n.children if isinstance(c, str))
            if len(text) != len("".join(str(c) for c in n.children)) or "`" in text:
                raise Unsupported("code")
            out.append(f"`{text}`")
        elif n.tag == "img":
            if "src" not in attrs:
                raise Unsupported("img without src")
            title = f' "{attrs["title"]}"' if attrs.get("title") else ""
            if '"' in attrs.get("title", "")[1:-1]:
                raise Unsupported("title quoting")
            alt = _escape(attrs.get("alt", ""))
            out.append(f"![{alt}]({_url(attrs['src'])}{title})" + _ial(attrs, skip=("src", "alt", "title")))
        elif n.tag == "a":
            if "href" not in attrs:
                raise Unsupported("a without href")
            inner = _inline(n.children)
            if not inner.strip():
                raise Unsupported("empty link")
            title = f' "{attrs["title"]}"' if attrs.get("title") else ""
            if '"' in attrs.get("title", ""):
                raise Unsupported("title quoting")
            out.append(f"[{inner}]({_url(attrs['href'])}{title})" + _ial(attrs, skip=("href", "title")))
    # a space right after a line break would start the next line with a space
    return re.sub(r"  \n +", "  \n", "".join(out))


def _block(n, indent=""):
    """Render one block node; returns a list of Markdown lines."""
    if n.tag == "#more":
        return [MORE]
    _attrs(n)
    if n.tag == "p":
        text = _inline(n.children).strip()
        if not text:
            return []
        if re.match(r"(\d+\.|[-+*>]|={2,}|-{2,})\s", text):
            raise Unsupported("paragraph starts like markdown syntax")
        return text.split("\n")
    if n.tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        text = _inline(n.children).strip()
        if "\n" in text:
            raise Unsupported("multi-line heading")
        return ["#" * int(n.tag[1]) + " " + text]
    if n.tag == "hr":
        return ["***"]
    if n.tag == "blockquote":
        lines = _blocks(n.children)
        return ["> " + l if l else ">" for l in lines]
    if n.tag in ("ul", "ol"):
        lines, number = [], 1
        for li in n.children:
            if isinstance(li, str):
                if li.strip():
                    raise Unsupported("text in list")
                continue
            if li.tag != "li":
                raise Unsupported("list child")
            _attrs(li)
            marker = f"{number}. " if n.tag == "ol" else "* "
            number += 1
            inline = [c for c in li.children if isinstance(c, str) or c.tag in INLINE]
            nested = [c for c in li.children if not isinstance(c, str) and c.tag in ("ul", "ol")]
            if len(inline) + len(nested) != len(li.children):
                raise Unsupported("block content in list item")
            if nested and li.children.index(nested[0]) < max((li.children.index(c) for c in inline), default=-1):
                raise Unsupported("text after nested list")
            text = _inline(inline).strip()
            if not text:
                raise Unsupported("empty list item")
            item = text.split("\n")
            lines.append(marker + item[0])
            lines += [" " * len(marker) + l for l in item[1:]]
            for sub in nested:
                lines += [" " * len(marker) + l for l in _block(sub)]
        return lines
    raise Unsupported(n.tag)


def _blocks(nodes):
    lines = []
    for n in nodes:
        if isinstance(n, str):
            if n.strip():
                raise Unsupported("text outside a block")
            continue
        if n.tag in INLINE:
            raise Unsupported("inline element outside a block")
        block = _block(n)
        if block:
            if lines:
                lines.append("")
            lines += block
    return lines


def convert(body):
    """HTML body -> Markdown, or None if the post uses anything outside the safe subset."""
    try:
        builder = TreeBuilder()
        builder.feed(body)
        builder.close()
        return "\n".join(_blocks(builder.root.children)).strip() + "\n"
    except (Unsupported, ValueError, IndexError):
        return None


# --- verification ------------------------------------------------------------------

class _Events(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        tag = {"b": "strong", "i": "em"}.get(tag, tag)
        a = {k: (v or "") for k, v in attrs if k not in IGNORED_ATTRS}
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            a.pop("id", None)  # kramdown's auto ids
        if tag == "img":
            a.setdefault("alt", "")  # Markdown always writes alt; missing and empty alt look the same
        if "class" in a:
            classes = " ".join(c for c in a["class"].split() if c not in IGNORED_CLASSES)
            a = {k: v for k, v in a.items() if k != "class"}
            if classes:
                a["class"] = classes
        self.events.append(("<", tag, tuple(sorted(a.items()))))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag not in VOID:
            self.events.append((">", {"b": "strong", "i": "em"}.get(tag, tag)))

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            if self.events and self.events[-1][0] == "t":
                self.events[-1] = ("t", self.events[-1][1] + text)
            else:
                self.events.append(("t", text))

    def handle_comment(self, data):
        self.events.append(("!", data))


def _normalize(text):
    events = _Events(text).events
    # Whitespace at block edges is not significant.
    out = []
    for i, e in enumerate(events):
        if e[0] == "t":
            t = e[1]
            prev = events[i - 1] if i else None
            nxt = events[i + 1] if i + 1 < len(events) else None
            if prev is None or (prev[0] in "<>" and prev[1] in BLOCK) or prev[0] == "!":
                t = t.lstrip()
            if nxt is None or (nxt[0] in "<>" and nxt[1] in BLOCK) or nxt[0] == "!":
                t = t.rstrip()
            if t:
                out.append(("t", t))
        else:
            out.append(e)
    return out


def equivalent(original_html, rendered_html):
    return _normalize(original_html) == _normalize(rendered_html)


def render(markdowns):
    """{key: markdown} -> {key: html}, rendered with Jekyll's kramdown settings."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kramdown_render.rb")
    env = dict(os.environ, RBENV_VERSION=os.environ.get("RBENV_VERSION", "3.1.2"))
    out = subprocess.run(["ruby", script], input=json.dumps(markdowns), capture_output=True,
                         text=True, check=True, env=env).stdout
    return json.loads(out)


def convert_verified(bodies):
    """{key: html} -> {key: markdown} for the bodies that convert *and* render back identically."""
    candidates = {k: md for k, md in ((k, convert(b)) for k, b in bodies.items()) if md}
    if not candidates:
        return {}
    rendered = render(candidates)
    return {k: md for k, md in candidates.items() if equivalent(bodies[k], rendered[k])}


# --- command line ------------------------------------------------------------------

def _split_front_matter(text):
    if text.startswith("---\n"):
        end = text.index("\n---\n", 4) + len("\n---\n")
        return text[:end], text[end:]
    return "", text


def main(argv):
    """python3 _migration/html2md.py [--dry-run] [_posts/….html …]

    Converts HTML posts to Markdown in place (foo.html -> foo.md), but only those that
    convert *and* render back identically. Without file arguments: all _posts/*.html."""
    import glob
    import sys
    dry = "--dry-run" in argv
    files = [a for a in argv if not a.startswith("--")]
    if not files:
        site = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        files = sorted(glob.glob(os.path.join(site, "_posts", "*.html")))
    parts = {f: _split_front_matter(open(f, encoding="utf-8").read()) for f in files}
    converted = convert_verified({f: body for f, (_, body) in parts.items()})
    for f in files:
        if f in converted and not dry:
            with open(f[:-len(".html")] + ".md", "w", encoding="utf-8") as out:
                out.write(parts[f][0] + converted[f])
            os.remove(f)
    verb = "would convert" if dry else "converted"
    print(f"{verb} {len(converted)} of {len(files)} HTML posts to Markdown; "
          f"{len(files) - len(converted)} stay HTML", file=sys.stderr)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
