# Generates the WordPress-style archive pages
#   /category/<slug>/   and   /tag/<slug>/
# using the original slugs from _data/categories.yml and _data/tags.yml,
# so the old category and tag URLs keep working.
module Volkersfreunde
  class TaxonomyPage < Jekyll::Page
    def initialize(site, dir, title, posts)
      @site = site
      @base = site.source
      @dir  = dir
      @name = "index.html"
      process(@name)
      @data = { "layout" => "taxonomy", "title" => title, "posts" => posts }
    end
  end

  class TaxonomyGenerator < Jekyll::Generator
    safe true

    def generate(site)
      build(site, site.categories, site.data["categories"], site.config["category_base"], "Kategorie")
      build(site, site.tags,       site.data["tags"],       site.config["tag_base"],      "Schlagwort")
    end

    private

    def build(site, index, terms, base, label)
      slugs = (terms || []).to_h { |t| [t["name"], t["slug"]] }
      index.each do |name, posts|
        slug = slugs[name] || Jekyll::Utils.slugify(name)
        dir  = File.join(base || "/", slug)
        site.pages << TaxonomyPage.new(site, dir, "#{label}: #{name}", posts.sort_by(&:date).reverse)
      end
    end
  end
end
