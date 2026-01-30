"""
Static HTML Generator for Validation Results

Creates self-contained HTML files with embedded table data, CSS, and JavaScript.
These files can be viewed offline and include SEO metadata (JSON-LD and hidden text).

Usage:
    from interface_lambda.utils.static_html_generator import StaticHTMLGenerator

    generator = StaticHTMLGenerator()
    html = generator.generate(
        table_metadata=metadata,
        title="My Table",
        subtitle="Generated 2024-01-15",
        description="Validation results for My Table",
        seo_content="Additional keywords for search engines",
        interactive_url="https://hyperplexity.com?mode=viewer&session=xxx"
    )
"""
import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


class StaticHTMLGenerator:
    """Generates standalone HTML files for validation results."""

    def __init__(self):
        self._template_cache = None
        self._css_cache = {}
        self._js_cache = None

    def generate(
        self,
        table_metadata: Dict[str, Any],
        title: str,
        subtitle: str = "",
        description: str = "",
        seo_content: str = "",
        interactive_url: str = ""
    ) -> str:
        """
        Generate a complete standalone HTML file.

        Args:
            table_metadata: The table_metadata.json content
            title: Page title (also used in <h1>)
            subtitle: Subtitle text (shown below title)
            description: Meta description for SEO
            seo_content: Hidden SEO content (white text)
            interactive_url: Link to interactive version

        Returns:
            Complete HTML string ready to save to file
        """
        # Load template and assets
        template = self._get_template()
        table_css = self._get_css()
        table_js = self._get_js()

        # Generate JSON-LD structured data
        json_ld = self._generate_json_ld(
            title=title,
            description=description,
            table_metadata=table_metadata
        )

        # Generate footer link if interactive URL provided
        footer_link = ""
        if interactive_url:
            footer_link = f' | <a href="{self._escape_html(interactive_url)}" target="_blank" rel="noopener">View Interactive Version</a>'

        # Build the HTML by replacing placeholders
        html = template
        html = html.replace('{{TITLE}}', self._escape_html(title))
        html = html.replace('{{SUBTITLE}}', self._escape_html(subtitle))
        html = html.replace('{{DESCRIPTION}}', self._escape_html(description or f"Validation results for {title}"))
        html = html.replace('{{TABLE_CSS}}', table_css)
        html = html.replace('{{TABLE_JS}}', table_js)
        html = html.replace('{{METADATA_JSON}}', json.dumps(table_metadata))
        html = html.replace('{{JSON_LD}}', json.dumps(json_ld, indent=2))
        html = html.replace('{{SEO_CONTENT}}', self._escape_html(seo_content))
        html = html.replace('{{FOOTER_LINK}}', footer_link)

        return html

    def _get_template(self) -> str:
        """Load the HTML template."""
        if self._template_cache:
            return self._template_cache

        # Try loading from bundled templates directory
        template_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'templates', 'standalone-table-template.html'),
            os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..',
                        'frontend', 'src', 'standalone-table-template.html'),
        ]

        for template_path in template_paths:
            try:
                if os.path.exists(template_path):
                    with open(template_path, 'r', encoding='utf-8') as f:
                        self._template_cache = f.read()
                        logger.info(f"[STATIC_HTML] Loaded template from {template_path}")
                        return self._template_cache
            except Exception as e:
                logger.warning(f"[STATIC_HTML] Could not load template from {template_path}: {e}")

        # Fallback to minimal embedded template
        logger.warning("[STATIC_HTML] Using minimal fallback template")
        self._template_cache = self._get_minimal_template()
        return self._template_cache

    def _get_css(self) -> str:
        """Load table CSS (07-tables.css)."""
        if 'table_css' in self._css_cache:
            return self._css_cache['table_css']

        css_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'templates', 'css', '07-tables.css'),
            os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..',
                        'frontend', 'src', 'styles', '07-tables.css'),
        ]

        for css_path in css_paths:
            try:
                if os.path.exists(css_path):
                    with open(css_path, 'r', encoding='utf-8') as f:
                        self._css_cache['table_css'] = f.read()
                        logger.info(f"[STATIC_HTML] Loaded CSS from {css_path}")
                        return self._css_cache['table_css']
            except Exception as e:
                logger.warning(f"[STATIC_HTML] Could not load CSS from {css_path}: {e}")

        # Fallback to minimal CSS
        logger.warning("[STATIC_HTML] Using minimal fallback CSS")
        self._css_cache['table_css'] = self._get_minimal_css()
        return self._css_cache['table_css']

    def _get_js(self) -> str:
        """Load interactive table JavaScript (16-interactive-table.js)."""
        if self._js_cache:
            return self._js_cache

        js_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'templates', 'js', '16-interactive-table.js'),
            os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..',
                        'frontend', 'src', 'js', '16-interactive-table.js'),
        ]

        for js_path in js_paths:
            try:
                if os.path.exists(js_path):
                    with open(js_path, 'r', encoding='utf-8') as f:
                        self._js_cache = f.read()
                        logger.info(f"[STATIC_HTML] Loaded JS from {js_path}")
                        return self._js_cache
            except Exception as e:
                logger.warning(f"[STATIC_HTML] Could not load JS from {js_path}: {e}")

        # Fallback to error message
        logger.error("[STATIC_HTML] Could not load interactive table JS")
        self._js_cache = '/* Interactive table JS not found - table will not be interactive */'
        return self._js_cache

    def _generate_json_ld(
        self,
        title: str,
        description: str,
        table_metadata: Dict[str, Any]
    ) -> Dict:
        """Generate JSON-LD structured data for SEO (schema.org Dataset)."""
        rows = table_metadata.get('rows', [])
        columns = table_metadata.get('columns', [])

        # Extract column names for variableMeasured
        column_names = [col.get('name', '') for col in columns if col.get('name')]

        return {
            "@context": "https://schema.org",
            "@type": "Dataset",
            "name": title,
            "description": description or f"Data table with {len(rows)} rows and {len(columns)} columns",
            "creator": {
                "@type": "Organization",
                "name": "Hyperplexity",
                "url": "https://hyperplexity.com"
            },
            "dateCreated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "variableMeasured": column_names[:20]  # Limit to first 20 columns
        }

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters to prevent XSS."""
        if not text:
            return ''
        return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))

    def _get_minimal_template(self) -> str:
        """Return a minimal template if the full one isn't available."""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE}}</title>
    <meta name="description" content="{{DESCRIPTION}}">
    <script type="application/ld+json">{{JSON_LD}}</script>
    <style>
        :root {
            --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            --border-radius: 8px;
            --font-size-base: 14px;
            --text-color: #333;
            --text-secondary: #666;
            --card-background: #fff;
            --primary-color: #28FF3A;
        }
        * { box-sizing: border-box; }
        body { font-family: var(--font-family); margin: 0; padding: 20px; background: #f5f5f5; color: var(--text-color); }
        .viewer-container { max-width: 1200px; margin: 0 auto; background: var(--card-background); border-radius: var(--border-radius); padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
        .viewer-header { margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #eee; }
        .viewer-title { margin: 0 0 5px 0; font-size: 1.5rem; font-weight: 600; }
        .viewer-subtitle { color: var(--text-secondary); margin: 0; }
        .viewer-footer { margin-top: 24px; padding-top: 16px; border-top: 1px solid #eee; text-align: center; color: var(--text-secondary); font-size: 13px; }
        .viewer-footer a { color: var(--primary-color); text-decoration: none; }
        .seo-content { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }
        {{TABLE_CSS}}
    </style>
</head>
<body>
    <div class="seo-content" aria-hidden="true">{{SEO_CONTENT}}</div>
    <div class="viewer-container">
        <div class="viewer-header">
            <h1 class="viewer-title">{{TITLE}}</h1>
            <p class="viewer-subtitle">{{SUBTITLE}}</p>
        </div>
        <div id="table-container"></div>
        <div class="viewer-footer">Generated by <a href="https://hyperplexity.com" target="_blank">Hyperplexity</a>{{FOOTER_LINK}}</div>
    </div>
    <script>window.TABLE_METADATA={{METADATA_JSON}};</script>
    <script>
        {{TABLE_JS}}
        (function(){
            var c=document.getElementById('table-container');
            if(window.TABLE_METADATA && typeof InteractiveTable!=='undefined'){
                c.innerHTML=InteractiveTable.render(window.TABLE_METADATA,{showGeneralNotes:true,showLegend:true});
                InteractiveTable.init();
            } else {
                c.innerHTML='<p style="color:#666;text-align:center;">Table could not be rendered.</p>';
            }
        })();
    </script>
</body>
</html>'''

    def _get_minimal_css(self) -> str:
        """Return minimal CSS for basic table display."""
        return '''
/* Minimal table CSS fallback */
.interactive-table-container { overflow-x: auto; margin: 20px 0; }
.interactive-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.interactive-table th, .interactive-table td { padding: 10px; border: 1px solid #e0e0e0; text-align: left; }
.interactive-table th { background: #f5f5f5; font-weight: 600; }
.interactive-table tr:hover { background: #f9f9f9; }
.confidence-high { background-color: rgba(40, 255, 58, 0.2); }
.confidence-medium { background-color: rgba(255, 235, 59, 0.2); }
.confidence-low { background-color: rgba(244, 67, 54, 0.2); }
.confidence-id { background-color: rgba(33, 150, 243, 0.2); }
.table-legend { display: flex; gap: 15px; margin-bottom: 15px; font-size: 13px; }
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-color { width: 16px; height: 16px; border-radius: 3px; }
.general-notes-box { background: #f0f7ff; border: 1px solid #cce5ff; border-radius: 8px; padding: 12px; margin-bottom: 15px; }
'''
