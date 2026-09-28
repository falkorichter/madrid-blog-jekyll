# Falko en Madrid — static Jekyll archive

The 2008/09 blog **madrid.falkorichter.de** ("Falko en Madrid – 5 Monate Spanien"),
converted from WordPress to a static Jekyll site with a port of its original theme
`falkoenmadrid` (based on *Beauty Bling*).

* [] bring back `madrid.falkorichter.de`
* [x] serve via github pages

```sh
bundle install
bundle exec jekyll serve      # http://localhost:4000
```

## What's here

| Path | What |
|---|---|
| `_layouts/`, `_includes/`, `assets/css/style.css` | the ported theme (changes marked `port:` in the CSS) |
| `_posts/` | 64 posts, original URLs `/<slug>/` |
| `_pages/` | Kontakt, Meine Karte, Über Madrid |
| `assets/galleries/<gallery>/` (+ `thumbs/`) | the 14 NextGEN galleries used by posts |
| `assets/images/YYYY/MM/` | other uploaded images |
| `assets/js/lightbox.js` | lightbox for gallery thumbnails and post images (←/→, swipe, Esc) |
| `_data/comments.json` | the 80 real comments, shown read-only (see [Comments](#comments)) |
| `_data/{categories,tags,blogroll}.json` | sidebar data; slugs keep `/category/…` and `/tag/…` URLs |
| `_data/moved_files.json` → `.htaccess` | 301 redirects from the old `/wp-content/…` file URLs |
| `_plugins/taxonomy_pages.rb` | generates the category/tag archive pages |
| `_migration/export_rest.py` | the exporter (see below) |

## Re-running the export

The content comes from the local, cleaned WordPress copy of the blog
(docker compose service `madrid`, http://localhost:8090, in the parent migration project):

```sh
python3 _migration/export_rest.py    # rewrites _posts, _pages, assets/galleries, assets/images, _data
```

It reads the REST API (`?rest_route=`) plus the DB for categories/tags (the 2008 DB has
"shared terms" that current WordPress reports wrongly) and the blogroll. It converts old Flash
YouTube/Vimeo embeds to iframes, moves every referenced file into `assets/`, and writes
`_migration/export-report.json`.

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
