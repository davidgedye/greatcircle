#!/usr/bin/env python3
"""Regenerate the content section of about.html from README.md.

Replaces everything between <!-- CONTENT START --> and <!-- CONTENT END -->
in about.html with the HTML-rendered README.md.

Requires: pip install markdown
"""
import re
import sys

try:
    import markdown
except ImportError:
    sys.exit("Missing dependency — run: pip install markdown")

START = '<!-- CONTENT START -->'
END   = '<!-- CONTENT END -->'

with open('README.md', encoding='utf-8') as f:
    md_text = f.read()

html = markdown.markdown(md_text, extensions=['tables', 'fenced_code'])

new_block = f'{START}\n{html}\n{END}'

with open('about.html', encoding='utf-8') as f:
    page = f.read()

pattern = re.escape(START) + '.*?' + re.escape(END)
updated, n = re.subn(pattern, new_block, page, flags=re.DOTALL)

if n == 0:
    sys.exit('Error: markers not found in about.html — add <!-- CONTENT START --> and <!-- CONTENT END -->')

with open('about.html', 'w', encoding='utf-8') as f:
    f.write(updated)

print('about.html updated from README.md')
