"""Convert docs/API_GUIDE.md to docs/API_GUIDE.html using the styling from xls2report_UI.py."""
import re
import os
import mistune
from bs4 import BeautifulSoup

highlight_color = "#08BD2E"

# ── utilities lifted from xls2report_UI.py ────────────────────────────────────

def preprocess_markdown(markdown_content, remove_after_keyword=None):
    """Table rows (lines containing |) are left untouched to avoid breaking markdown table syntax."""
    lines = markdown_content.split('\n')
    processed = []
    for line in lines:
        if '|' in line:
            processed.append(line)
        else:
            line = re.sub(r'^-+$', '', line)
            line = re.sub(r' -([a-zA-Z0-9])', r' - \1', line)
            line = re.sub(r'(?i)(\*\*Story:\*\*.+)', r'\n\n\1\n\n', line)
            processed.append(line)
    markdown_content = '\n'.join(processed)
    if remove_after_keyword:
        pattern = re.compile(re.escape(remove_after_keyword) + r'.*$', re.DOTALL)
        markdown_content = re.sub(pattern, '', markdown_content)
    return markdown_content


def replace_headers_with_spans(html_content):
    """Replace <hN> tags with styled <span class='md-headingN'> elements."""
    for i in range(1, 6):
        html_content = re.sub(
            rf'<h{i}>(.+?)</h{i}>',
            rf'<span class="md-heading{i}">\1</span>',
            html_content,
        )
    return html_content


# ── CSS (same as xls2report_UI.py) ────────────────────────────────────────────

CSS = (
    "@import url('https://fonts.googleapis.com/css2?family=Open+Sans&display=swap');"
    "body { font-family: 'Calibri', 'Open Sans', sans-serif; font-size: 15px; max-width: 960px; margin: 0 auto; padding: 2em; }"
    f".highlight {{ color: {highlight_color}; font-size: 1.4em; }}"
    f".md-heading1, .md-heading2, .md-heading3, .md-heading4, .md-heading5 {{ color: {highlight_color}; display: block; margin-top: 1.2em; margin-bottom: 0.4em; font-weight: bold; }}"
    ".md-heading1 { font-size: 2em; } .md-heading2 { font-size: 1.65em; } .md-heading3 { font-size: 1.35em; }"
    ".md-heading4 { font-size: 1.15em; } .md-heading5 { font-size: 1.05em; }"
    "table { border-collapse: collapse; vertical-align: top; width: 100%; table-layout: fixed; }"
    "th, td { border: 2px solid #CED0CE; padding: 8px; text-align: left; vertical-align: top; overflow-wrap: break-word; font-size: 1em; }"
    "thead th { background-color:#DDFFDD; border-bottom: 2px solid #000; }"
    "pre { background-color: #f4f4f4; border: 1px solid #ddd; border-left: 3px solid #f36d33;"
    " color: #444; page-break-inside: avoid; font-family: monospace; font-size: 0.88em; line-height: 1.4;"
    " margin-bottom: 1.6em; max-width: 100%; overflow: auto; padding: 1em 1.5em; display: block;"
    " word-wrap: break-word; white-space: pre-wrap; }"
    "code { background-color: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; font-size: 0.9em; }"
    "blockquote { border-left: 4px solid #CED0CE; margin: 0.5em 0; padding: 0.5em 1em;"
    " background: #f9f9f9; color: #555; }"
    "a { color: #0066cc; }"
)

# ── main ──────────────────────────────────────────────────────────────────────

def md_to_html(md_path: str, out_path: str) -> None:
    with open(md_path, encoding="utf-8") as f:
        md_content = f.read()

    md_renderer = mistune.create_markdown(plugins=["table"])

    processed = preprocess_markdown(md_content)
    body_html = md_renderer(processed)
    body_html = replace_headers_with_spans(body_html)

    soup = BeautifulSoup(
        f'<html><head><meta charset="utf-8"><style>{CSS}</style></head><body>{body_html}</body></html>',
        "html.parser",
    )


    with open(out_path, "w", encoding="utf-8") as f:
        f.write(soup.prettify())

    print(f"Written: {out_path}")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    md_to_html(
        os.path.join(here, "..", "mcp", "README.md"),
        os.path.join(here, "API_GUIDE.html"),
    )
