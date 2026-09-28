# Prefixes root-relative links with site.baseurl in the rendered HTML, so the
# site also works under a sub-path (GitHub Pages: /volkersfreunde-jekyll/).
# The layouts already use relative_url, but the imported post bodies contain
# hard-coded /assets/... and /<slug>/ links (and are rendered without Liquid).
# With baseurl "" (www.volkersfreunde.de) this does nothing.
module Volkersfreunde
  module BaseurlLinks
    ATTRIBUTES = %w[href src srcset action poster data].freeze

    def self.rewrite(doc)
      baseurl = doc.site.config["baseurl"].to_s.chomp("/")
      return if baseurl.empty? || doc.output.nil? || !doc.output_ext.to_s.start_with?(".htm")

      # attr="/x" -> attr="<baseurl>/x", except protocol-relative //host and
      # links that already carry the baseurl (relative_url output).
      skip = Regexp.escape(baseurl.delete_prefix("/"))
      pattern = %r{(\s(?:#{ATTRIBUTES.join("|")})=["'])/(?!/|#{skip}(?:/|["'#?]))}
      doc.output = doc.output.gsub(pattern) { "#{Regexp.last_match(1)}#{baseurl}/" }
    end
  end
end

Jekyll::Hooks.register [:pages, :documents], :post_render do |doc|
  Volkersfreunde::BaseurlLinks.rewrite(doc)
end
