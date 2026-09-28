# Falko en Madrid — static Jekyll archive

The 2008/09 blog **madrid.falkorichter.de** ("Falko en Madrid – 5 Monate Spanien"),
converted from WordPress to a static Jekyll site with a port of its original theme
`falkoenmadrid` (based on *Beauty Bling*).

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
| `_data/comments.json` | the 80 real comments, shown read-only (the form is gone) |
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

## Dropped on purpose
Google Analytics, the Google AJAX video bar (API is gone), the Meta/login widget, the
comment form, the **Newsletter** page (Subscribe2 plugin) and the **Impressum** page (it only
contained the old Google Analytics notice). A real Impressum is still needed before publishing.
