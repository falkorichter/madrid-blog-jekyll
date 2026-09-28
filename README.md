# Falko en Madrid — static Jekyll archive

The 2008/09 blog **madrid.falkorichter.de** ("Falko en Madrid – 5 Monate Spanien"),
converted from WordPress to a static Jekyll site with a port of its original theme
`falkoenmadrid` (based on *Beauty Bling*).

* [ ] bring back `madrid.falkorichter.de`
* [x] serve via github pages

```sh
bundle install
bundle exec jekyll serve      # http://localhost:4000
```

Search (`/suche/`) uses [Pagefind](https://pagefind.app): the index is built from the
finished HTML after `jekyll build` (the Pages workflow does this). `jekyll serve` has no
index; to try the search locally:

```sh
bundle exec jekyll build && npx -y pagefind@1.5.2 --site _site --serve   # http://localhost:1414/suche/
```

Indexed: post title and text (`data-pagefind-body` in `_layouts/post.html`), with year and
category filters (`_includes/search-meta.html`); comments and the meta line are left out.

## What's here

| Path | What |
|---|---|
| `_layouts/`, `_includes/`, `assets/css/style.css` | the ported theme (changes marked `port:` in the CSS) |
| `_posts/` | 64 posts (Markdown where possible, see below), original URLs `/<slug>/` |
| `_pages/` | Kontakt, Meine Karte, Über Madrid, and the new `/statistiken/` (numbers counted at build time, export numbers from `_data/export_report.json`) |
| `assets/galleries/<gallery>/` (+ `thumbs/`) | the 14 NextGEN galleries used by posts |
| `assets/images/YYYY/MM/` | other uploaded images |
| `assets/js/lightbox.js` | lightbox for gallery thumbnails and post images (←/→, swipe, Esc) |
| `_data/comments.json` | the 80 real comments, shown read-only (see [Comments](#comments)) |
| `_data/{categories,tags,blogroll}.json` | sidebar data; slugs keep `/category/…` and `/tag/…` URLs |
| `feed-redirect.html` | `/feed/` (the old WordPress feed URL) forwards to `/feed.xml` |
| `_plugins/taxonomy_pages.rb` | generates the category/tag archive pages |
| `_migration/export_rest.py` | the exporter (see below) |
| `_migration/html2md.py`, `kramdown_render.rb`, `compare_builds.py` | HTML → Markdown conversion and its checks (see [Markdown posts](#markdown-posts)) |

## Re-running the export

The content comes from the local, cleaned WordPress copy of the blog
(docker compose service `madrid`, http://localhost:8090, in the parent migration project):

```sh
python3 _migration/export_rest.py    # rewrites _posts, _pages, assets/galleries, assets/images, _data
```

It reads the REST API (`?rest_route=`) plus the DB for categories/tags (the 2008 DB has
"shared terms" that current WordPress reports wrongly) and the blogroll. It converts old Flash
YouTube/Vimeo embeds to iframes, moves every referenced file into `assets/`, and writes
`_data/export_report.json`.

## Markdown posts

Posts are stored as **Markdown** (`_posts/*.md`) where that is possible *without changing the
page*, and stay **HTML** (`_posts/*.html`) otherwise — currently 20 of 64 posts are
Markdown. Posts with embeds (videos, maps, galleries), `<div>`/`<span>` markup, inline styles etc.
stay HTML on purpose.

How it works (`_migration/html2md.py`, used by the exporter):

1. **Convert** only a safe subset of HTML: paragraphs, line breaks, links, bold/italic, inline
   code, headings, lists, quotes, rules and images. Image size and alignment and link targets are
   kept as kramdown attribute lists, e.g. `![Foto](/assets/…/a.jpg){: .alignleft width="300"}`.
   Anything else → the post stays HTML.
2. **Verify**: the Markdown is rendered with Jekyll's own Markdown converter and default
   kramdown settings (`_migration/kramdown_render.rb`) and compared with the original HTML
   (normalized: whitespace, entities and attribute order don't count; `loading`/`decoding`
   and the `wp-block-paragraph` class are ignored). Only an identical result becomes `.md`.

Tools:

```sh
python3 _migration/html2md.py --dry-run          # how many HTML posts would convert
python3 _migration/html2md.py [_posts/x.html …]  # convert in place (x.html -> x.md), verified
python3 _migration/compare_builds.py [REV]       # build REV (default HEAD) and the working
                                                 # tree, compare every generated page
```

`compare_builds.py` exits with 1 if the content of any post or page differs. Switching to
Markdown changed no post content; the only differences were list pages (category/tag archives),
whose short 55-word teasers now end a word or two earlier, and `<meta name="description">`,
which shows `…`/`–` instead of `&#8230;`/`&#8211;` (fixed for HTML posts too).
Needs Ruby with Jekyll (`RBENV_VERSION=3.1.2` locally).

## GitHub Pages

https://falkorichter.github.io/madrid-blog-jekyll/ is built by `.github/workflows/pages.yml`
on every push to `main` (repo setting *Pages → Source: GitHub Actions*). Pages' built-in build
would not work: it runs neither `_plugins/` (no category/tag pages) nor Jekyll 4, and does not
know the `/madrid-blog-jekyll/` sub-path. The workflow passes that sub-path as `--baseurl`;
`_plugins/baseurl_links.rb` prefixes the hard-coded `/assets/…` and `/<slug>/` links inside the
exported posts and comments. `_config.yml` keeps `baseurl: ""` for a root domain such as
madrid.falkorichter.de, where the plugin does nothing. The workflow also sets `url` to the Pages
address, so canonical links and the feed point there.

The site is **static only** (no `.htaccess`, no server rules): post URLs `/<slug>/` are folders
with `index.html`, `404.html` is used by the host, the feed is `/feed.xml`. Old image URLs
(`/wp-content/…`) are intentionally not redirected; only the post URLs are preserved.

## Comments

The blog's **80 real comments** (31 Aug 2008 – 17 Sep 2009, on 30 posts) are part of the
archive, but **read-only**: a static site has no server to receive new comments, so there is
no comment form ("Sorry, the comment form is closed at this time.", as on the old blog).

**Where they come from.** The old database also held ~1,500 spam comments from 2014–2019.
Those were deleted in the local WordPress copy before the export (see the migration
project's README); only the real comments are left there. The exporter reads them from
the REST API (`?rest_route=/wp/v2/comments`, oldest first), keeps only `approved` ones on
published posts, and writes them to **`_data/comments.json`**, one entry per comment:

```json
{
 "id": 2,
 "url": "/falko-en-madrid-5barcelona/",
 "post_title": "Falko en Madrid 5 – Barcelona",
 "author": "Martin",
 "author_url": "http://www.knorrpage.de",
 "date": "2008-08-31 00:05:20",
 "content": "<p>Juhu, neue Videos! …</p>"
}
```

`url` is the permalink of the post the comment belongs to; `content` is the HTML as
WordPress displayed it. Only public fields are exported — no e-mail or IP addresses.

**How they are shown.** Everything is plain Liquid, no plugin or JavaScript:

| Where | Include | How |
|---|---|---|
| under each post | `_includes/comments.html` | `site.data.comments \| where: "url", page.url` → heading "No Comments / 1 Comment / n Comments", then the list as in the old `comments.php`: text, then "Comment by *Name* — date @ time". The name links to the author's website (`rel="external nofollow ugc"`) if one was given; each comment has an anchor `#comment-<id>`. |
| home page / archives | `_includes/comment-count.html` | "Comments (n)" in the grey feedback bar, linking to `<post>#comments` |
| sidebar "letzte Kommentare" | `_includes/sidebar.html` | the 3 newest comments (sorted by `date`): "Name on *Post title*", linking to `<post>#comment-<id>` |

**Changing them.** To remove a single comment, delete its entry from `_data/comments.json`
(or delete it in WordPress and re-run the export). To drop comments entirely, empty the file
to `[]`: the posts then show "No Comments" and the sidebar block disappears.

## Dropped on purpose
Google Analytics, the Google AJAX video bar (API is gone), the Meta/login widget, the
comment form, the **Newsletter** page (Subscribe2 plugin) and the **Impressum** page (it only
contained the old Google Analytics notice). A real Impressum is still needed before publishing.
