# Renders Markdown exactly like the Jekyll build does (Jekyll's own Markdown converter with the
# default kramdown settings; neither site overrides them). Used by html2md.py to verify that a
# converted post renders back to the same HTML.
#   stdin:  {"key": "markdown", …}   stdout: {"key": "html", …}
require "json"
require "jekyll"

config = Jekyll::Configuration.from({})
converter = Jekyll::Converters::Markdown.new(config)
input = JSON.parse($stdin.read)
puts JSON.generate(input.transform_values { |md| converter.convert(md) })
