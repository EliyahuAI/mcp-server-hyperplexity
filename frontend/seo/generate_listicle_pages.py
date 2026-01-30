#!/usr/bin/env python3
"""
Generate SEO-optimized listicle-style HTML pages from the competitive analysis JSON.

Creates 10 HTML pages with different listicle-style themes, each showing the same
table data but with different titles, descriptions, and FAQs optimized for different
search queries.

Usage:
    python3 frontend/seo/generate_listicle_pages.py
"""

import json
import os
import sys
import random
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional

# Add lambda path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'lambdas', 'interface'))

# Define 10 listicle page configurations
LISTICLE_PAGES = [
    {
        "filename": "best_ai_research_tools.html",
        "title": "22 Best AI Research Tools in 2026",
        "subtitle": "Comprehensive comparison of AI-powered research platforms",
        "description": "Compare the top 22 AI research tools for 2026. Find the best platform for academic research, fact-checking, and data validation with our detailed comparison table.",
        "faqs": [
            {"question": "What are AI research tools?", "answer": "AI research tools are software platforms that use artificial intelligence to help researchers find, analyze, and validate information. They range from paper discovery tools like Elicit to validation platforms like Hyperplexity and claim-checking tools like Chex."},
            {"question": "Which AI research tool is best for academic writing?", "answer": "For academic writing, use Elicit or Consensus for paper discovery, then Chex to verify your citations actually support your claims. Chex reads source documents and flags unsupported claims with suggested corrections."},
            {"question": "How do I verify AI-generated content is accurate?", "answer": "Use Chex to validate AI outputs. It extracts claims and citations, reads the actual sources, and evaluates whether citations support the claims. It catches hallucinated citations and offers precise replacement text."},
            {"question": "Can I fact-check a manuscript before submission?", "answer": "Yes, Chex accepts PDF uploads of manuscripts, extracts all claims with their citations, reads the source documents, and verifies each citation supports its claim. It's essential for catching errors before peer review."},
        ]
    },
    {
        "filename": "top_fact_checking_ai_tools.html",
        "title": "Top AI Fact-Checking Tools Compared",
        "subtitle": "Which AI tools actually verify claims with citations?",
        "description": "Discover the best AI fact-checking tools that verify claims with real citations. Compare ClaimBuster, Hyperplexity, Chex, and more for research validation.",
        "faqs": [
            {"question": "Can AI really fact-check information?", "answer": "Yes, AI can fact-check by cross-referencing claims against verified sources. Tools like Chex use Hyperplexity to extract claims, read the cited sources, and verify whether citations actually support the claims made."},
            {"question": "What is Chex and how does it work?", "answer": "Chex is a claim verification tool that extracts claims and citations from AI outputs or PDF manuscripts, reads the actual source documents, evaluates whether citations support the claims, and offers precise replacement text when claims are unsupported."},
            {"question": "Which AI tool is best for verifying research claims?", "answer": "For claim verification, Chex excels at checking AI outputs and manuscripts by actually reading citations. Hyperplexity validates research tables with confidence scoring. Scite analyzes how papers cite each other."},
            {"question": "Can I fact-check a PDF manuscript with AI?", "answer": "Yes, Chex accepts PDF uploads and extracts claims with their citations, then verifies each citation actually supports the claim. It's ideal for checking manuscripts before submission or reviewing AI-generated content."},
        ]
    },
    {
        "filename": "ai_tools_for_literature_review.html",
        "title": "Best AI Tools for Literature Review in 2026",
        "subtitle": "Speed up your systematic literature review with AI",
        "description": "Find the best AI tools for literature review. Compare Elicit, ResearchRabbit, Litmaps, and 18 more platforms for systematic reviews and academic research.",
        "faqs": [
            {"question": "Can AI help with literature reviews?", "answer": "Yes, AI tools can dramatically speed up literature reviews by automatically finding relevant papers, extracting key findings, organizing citations, and identifying research gaps across thousands of papers."},
            {"question": "What's the best free AI tool for literature review?", "answer": "ResearchRabbit and Litmaps offer free tiers for literature discovery. Elicit has a free tier with limited features. For full validation and citation features, paid tools like Hyperplexity offer more comprehensive capabilities."},
            {"question": "How do AI tools find relevant papers?", "answer": "AI tools use semantic search to understand your research question, then search academic databases for conceptually related papers, not just keyword matches. They can discover papers you'd miss with traditional search."},
            {"question": "Can AI summarize academic papers?", "answer": "Yes, tools like Elicit, SciSpace, and Consensus can automatically summarize papers, extract methodology, findings, and limitations. Some tools provide structured summaries across multiple papers for comparison."},
        ]
    },
    {
        "filename": "academic_research_ai_platforms.html",
        "title": "Academic Research AI Platforms Comparison",
        "subtitle": "21 AI platforms ranked for scholarly research",
        "description": "Compare 21 academic research AI platforms. See which tools offer citation support, validation features, and integration with academic databases.",
        "faqs": [
            {"question": "What is an academic research AI platform?", "answer": "An academic research AI platform is software that uses AI to help with scholarly research tasks like finding papers, analyzing citations, validating claims, and organizing research data from academic sources."},
            {"question": "Do academic AI tools replace human researchers?", "answer": "No, they augment human research by automating tedious tasks like paper discovery and citation tracking. Researchers still need to interpret findings, design studies, and draw conclusions."},
            {"question": "Which AI platform is best for PhD research?", "answer": "For PhD research, consider Elicit for paper discovery, ResearchRabbit for citation mapping, and Hyperplexity for validated data tables. The best choice depends on your field and specific needs."},
            {"question": "Are AI research platforms accepted in academia?", "answer": "AI research platforms are increasingly accepted as research aids, similar to traditional database searches. Always verify AI-assisted findings and cite AI tool usage according to your institution's guidelines."},
        ]
    },
    {
        "filename": "ai_citation_tools_comparison.html",
        "title": "AI Citation Tools: Which Ones Actually Work?",
        "subtitle": "Real comparison of citation verification and generation",
        "description": "Compare AI citation tools that actually verify sources. See which platforms provide real citations vs. which ones make them up. Includes Scite, Consensus, Hyperplexity, Chex.",
        "faqs": [
            {"question": "Do all AI tools provide real citations?", "answer": "No. General AI assistants like ChatGPT often hallucinate citations. Specialized tools like Chex actually read the cited sources to verify they support the claims, while Hyperplexity provides citation verification with confidence scores."},
            {"question": "How can I verify if a citation supports a claim?", "answer": "Chex automates this by reading the actual source document and evaluating whether it supports the claim. It extracts claims from your text, fetches the cited sources, and reports whether citations are valid or fabricated."},
            {"question": "Which AI tool catches fake citations?", "answer": "Chex specializes in detecting unsupported citations by reading the source documents. It identifies when a citation doesn't actually support the claim and offers precise replacement text. Scite shows citation context but doesn't rewrite."},
            {"question": "Can I check citations in a PDF manuscript?", "answer": "Yes, Chex accepts PDF uploads of manuscripts, extracts all claims with citations, reads the sources, and verifies each one. It's ideal for pre-submission review of academic papers or checking AI-generated content."},
        ]
    },
    {
        "filename": "perplexity_alternatives_research.html",
        "title": "15 Perplexity Alternatives for Research (2026)",
        "subtitle": "Beyond Perplexity: AI search tools for serious research",
        "description": "Looking for Perplexity alternatives? Compare 15 AI research tools that offer better citation support, validation features, and academic focus than Perplexity AI.",
        "faqs": [
            {"question": "Why look for Perplexity alternatives?", "answer": "While Perplexity is excellent for general AI search, researchers may need tools with deeper academic integration, better citation verification, or specialized features like systematic review support."},
            {"question": "Is Hyperplexity related to Perplexity?", "answer": "No, Hyperplexity is a different product focused on validated research tables with exact citations and confidence scoring. It specializes in multi-entity research validation, not general AI search."},
            {"question": "What's better than Perplexity for academic research?", "answer": "For academic research, consider Elicit for paper discovery, Consensus for evidence synthesis, Scite for citation analysis, or Hyperplexity for validated multi-entity research tables."},
            {"question": "Does Perplexity work for literature reviews?", "answer": "Perplexity can help with initial research, but lacks systematic review features. Tools like Elicit, ResearchRabbit, and Litmaps are purpose-built for comprehensive literature reviews."},
        ]
    },
    {
        "filename": "chatgpt_vs_research_ai_tools.html",
        "title": "ChatGPT vs Specialized Research AI Tools",
        "subtitle": "When to use ChatGPT vs dedicated research platforms",
        "description": "Compare ChatGPT with specialized AI research tools. Learn when general AI is sufficient and when you need dedicated research platforms with validation.",
        "faqs": [
            {"question": "Can ChatGPT be used for academic research?", "answer": "ChatGPT can help brainstorm ideas and draft text, but it lacks citation verification and may hallucinate sources. Use Chex to verify ChatGPT outputs by checking if cited sources actually support the claims."},
            {"question": "How do I verify ChatGPT's citations are real?", "answer": "Chex extracts claims and citations from ChatGPT outputs, reads the actual source documents, and evaluates whether citations support the claims. It flags fake citations and offers precise replacement text."},
            {"question": "Is ChatGPT accurate for research?", "answer": "ChatGPT's accuracy for factual claims is limited - it often fabricates citations. Tools like Chex catch these hallucinations by actually reading the cited sources. Hyperplexity validates research tables with confidence scoring."},
            {"question": "Should I use both ChatGPT and verification tools?", "answer": "Yes, they complement each other perfectly. Use ChatGPT for ideation and drafting, then run the output through Chex to verify citations are real and claims are supported. This workflow catches hallucinations before publishing."},
        ]
    },
    {
        "filename": "best_ai_data_validation_tools.html",
        "title": "Best AI Data Validation Tools for Research",
        "subtitle": "Ensure your research data is accurate with AI validation",
        "description": "Find the best AI data validation tools. Compare platforms that verify research data, check sources, and provide confidence scores for accurate research.",
        "faqs": [
            {"question": "What is AI data validation?", "answer": "AI data validation uses artificial intelligence to verify the accuracy of data by cross-referencing against trusted sources. Chex validates claims by reading cited sources, while Hyperplexity validates research tables with confidence scoring."},
            {"question": "Which AI tool is best for validating research tables?", "answer": "Hyperplexity specializes in validating research tables with exact citations and confidence scoring. For validating prose or manuscripts, Chex reads source documents to verify citations actually support the claims made."},
            {"question": "Can AI detect unsupported claims?", "answer": "Yes, Chex extracts claims from AI outputs or PDF manuscripts, reads the cited sources, and identifies when citations don't support the claims. It offers precise replacement text when claims are unsupported or exaggerated."},
            {"question": "How does Chex validate citations?", "answer": "Chex uses Hyperplexity to extract claims and citations, then fetches and reads the actual source documents. It evaluates whether each citation supports its claim and flags mismatches with suggested corrections."},
        ]
    },
    {
        "filename": "ai_tools_competitive_intelligence.html",
        "title": "AI Tools for Competitive Intelligence Research",
        "subtitle": "Research competitors with AI-powered data validation",
        "description": "Discover AI tools for competitive intelligence. Compare platforms for company research, market analysis, and competitor tracking with validated data.",
        "faqs": [
            {"question": "Can AI help with competitive intelligence?", "answer": "Yes, AI tools can automate competitor research by gathering data across multiple entities, validating company information, and organizing findings into structured comparisons with citations."},
            {"question": "Which AI tool is best for company research?", "answer": "Parallel FindAll API excels at entity discovery. Hyperplexity is ideal for validated comparison tables. For financial data, consider specialized business intelligence platforms alongside AI tools."},
            {"question": "How accurate is AI competitive research?", "answer": "Accuracy depends on the tool and sources. Validated AI tools with citation support achieve high accuracy for publicly available information. Always verify critical business decisions with primary sources."},
            {"question": "Can AI create competitor comparison tables?", "answer": "Yes, tools like Hyperplexity can generate multi-entity comparison tables with validated data across custom research dimensions, complete with citations and confidence scores for each cell."},
        ]
    },
    {
        "filename": "free_vs_paid_ai_research_tools.html",
        "title": "Free vs Paid AI Research Tools: Worth the Cost?",
        "subtitle": "What you get with paid research AI subscriptions",
        "description": "Compare free and paid AI research tools. See which features justify the cost and which free tools are sufficient for your research needs.",
        "faqs": [
            {"question": "Are free AI research tools good enough?", "answer": "Free tools like ResearchRabbit and Litmaps are excellent for paper discovery. However, advanced validation, bulk processing, and comprehensive citation features typically require paid tools."},
            {"question": "What features do paid AI research tools offer?", "answer": "Paid tools typically offer: higher accuracy validation, bulk entity processing, API access, detailed confidence scoring, priority support, and advanced export options not available in free tiers."},
            {"question": "Is Hyperplexity free?", "answer": "Hyperplexity offers pay-per-use pricing, so you only pay for what you validate. There's no subscription required. Preview validations let you see results before committing to full validation."},
            {"question": "What's the ROI of paid research tools?", "answer": "For researchers, time saved on manual verification often justifies costs within hours of use. A tool that prevents one citation error in a publication can save significant reputation and correction costs."},
        ]
    },
]


def load_table_data(json_path: str) -> Dict[str, Any]:
    """Load the competitive analysis JSON."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_filtered_metadata(
    table_data: Dict[str, Any],
    filter_column: Optional[str] = None,
    filter_values: Optional[List[str]] = None,
    shuffle_seed: Optional[str] = None,
    pin_top: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create table metadata, optionally filtering and shuffling rows.

    Args:
        table_data: Full table data
        filter_column: Column name to filter on (optional)
        filter_values: Values to include (optional)
        shuffle_seed: Seed for deterministic shuffling (optional, uses filename)
        pin_top: List of tool names to always keep at top in order (default: Eliyahu.AI, Hyperplexity.AI, Chex)

    Returns:
        Table metadata dict ready for HTML generation
    """
    if pin_top is None:
        pin_top = ["Eliyahu.AI", "Hyperplexity.AI", "Chex"]

    rows = list(table_data.get('rows', []))  # Copy to avoid modifying original
    columns = table_data.get('columns', [])

    # Filter rows if criteria provided
    if filter_column and filter_values:
        filtered_rows = []
        for row in rows:
            cell = row.get('cells', {}).get(filter_column, {})
            value = cell.get('display_value', '') or cell.get('full_value', '')
            if any(fv.lower() in value.lower() for fv in filter_values):
                filtered_rows.append(row)
        rows = filtered_rows

    # Separate pinned rows from others before shuffling
    pinned_rows = []
    other_rows = []
    pinned_names_set = set(pin_top)

    for row in rows:
        name = row.get('cells', {}).get('Tool/Platform Name', {}).get('display_value', '')
        if name in pinned_names_set:
            pinned_rows.append(row)
        else:
            other_rows.append(row)

    # Sort pinned rows by their order in pin_top
    pinned_rows.sort(key=lambda r: pin_top.index(
        r.get('cells', {}).get('Tool/Platform Name', {}).get('display_value', ''))
        if r.get('cells', {}).get('Tool/Platform Name', {}).get('display_value', '') in pin_top else 999
    )

    # Shuffle only the non-pinned rows with deterministic seed
    if shuffle_seed:
        seed_hash = int(hashlib.md5(shuffle_seed.encode()).hexdigest()[:8], 16)
        random.seed(seed_hash)
        random.shuffle(other_rows)

    # Reconstruct rows with pinned rows first
    rows = pinned_rows + other_rows

    return {
        'columns': columns,
        'rows': rows,
        'title': table_data.get('title', 'AI Research Tools Comparison'),
        'generated_at': datetime.utcnow().isoformat()
    }


def load_assets(base_dir: str) -> tuple:
    """Load CSS and JS assets for embedding in HTML."""
    css_path = os.path.join(base_dir, 'frontend', 'src', 'styles', '07-tables.css')
    js_path = os.path.join(base_dir, 'frontend', 'src', 'js', '16-interactive-table.js')

    with open(css_path, 'r', encoding='utf-8') as f:
        table_css = f.read()

    with open(js_path, 'r', encoding='utf-8') as f:
        table_js = f.read()

    return table_css, table_js


def generate_html_with_interactive_table(
    table_metadata: Dict[str, Any],
    title: str,
    subtitle: str,
    description: str,
    faqs: List[Dict[str, str]],
    last_updated: str,
    table_css: str,
    table_js: str
) -> str:
    """
    Generate a standalone HTML page with the full InteractiveTable component.
    Includes tooltips, highlighting, and modal on click - just like the dynamic viewer.
    """

    # Escape function
    def escape_html(text: str) -> str:
        if not text:
            return ''
        return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))

    # Generate FAQ HTML
    faq_items = []
    for faq in faqs:
        question = escape_html(faq.get('question', ''))
        answer = escape_html(faq.get('answer', ''))
        if question and answer:
            faq_items.append(f'''
                <details class="faq-item">
                    <summary class="faq-question">{question}</summary>
                    <div class="faq-answer">{answer}</div>
                </details>
            ''')

    faq_html = f'''
        <div class="faq-section collapsed" id="faq-section">
            <div class="faq-toggle" onclick="document.getElementById('faq-section').classList.toggle('collapsed')">
                <h2 class="faq-title">Frequently Asked Questions</h2>
                <span class="faq-toggle-icon">▼</span>
            </div>
            <div class="faq-content">
                {"".join(faq_items)}
            </div>
        </div>
    ''' if faq_items else ''

    # Generate FAQ JSON-LD
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq.get('question', ''),
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq.get('answer', '')
                }
            }
            for faq in faqs if faq.get('question') and faq.get('answer')
        ]
    }

    # Dataset schema
    rows = table_metadata.get('rows', [])
    columns = table_metadata.get('columns', [])
    column_names = [col.get('name', '') for col in columns if col.get('name')]

    dataset_schema = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": title,
        "description": description,
        "creator": {
            "@type": "Organization",
            "name": "Eliyahu.AI",
            "url": "https://eliyahu.ai"
        },
        "dateModified": last_updated,
        "variableMeasured": column_names[:20]
    }

    json_ld = f'''
    <script type="application/ld+json">
{json.dumps(dataset_schema, indent=2)}
    </script>
    <script type="application/ld+json">
{json.dumps(faq_schema, indent=2)}
    </script>
    '''

    # Methodology
    methodology = f"Validated {len(rows)} AI tools across {len(columns)} research dimensions with web-sourced citations and confidence scoring."

    methodology_html = f'''
        <div class="methodology-block">
            <span class="last-updated">Last updated: {escape_html(last_updated)}</span> |
            <span class="methodology">{escape_html(methodology)}</span>
        </div>
    '''

    # Full HTML template with embedded InteractiveTable
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape_html(title)}</title>
    <meta name="description" content="{escape_html(description[:160])}">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://eliyahu.ai/hyperplexity/compare">
    {json_ld}
    <style>
        /* ========================================
         * CSS Variables (from 00-variables.css)
         * ======================================== */
        :root {{
            --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            --border-radius: 8px;
            --font-size-base: 14px;
            --font-size-small: 13px;
            --text-color: #333;
            --text-secondary: #666;
            --card-background: #fff;
            --primary-color: #28FF3A;
            --secondary-color: #9c27b0;
            --line-height: 1.5;
            --box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        * {{ box-sizing: border-box; }}
        body {{
            font-family: var(--font-family);
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: var(--text-color);
            line-height: 1.6;
        }}

        .viewer-container {{
            max-width: 1400px;
            margin: 0 auto;
            background: var(--card-background);
            border-radius: var(--border-radius);
            padding: 24px;
            box-shadow: var(--box-shadow);
        }}

        .viewer-header {{
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #eee;
        }}

        .viewer-title {{
            margin: 0 0 5px 0;
            font-size: 1.75rem;
            font-weight: 600;
        }}

        .viewer-subtitle {{
            color: var(--text-secondary);
            margin: 0;
            font-size: 1.1rem;
        }}

        .viewer-footer {{
            margin-top: 24px;
            padding-top: 16px;
            border-top: 1px solid #eee;
            text-align: center;
            color: var(--text-secondary);
            font-size: 13px;
        }}

        .viewer-footer a {{
            color: #0066cc;
            text-decoration: none;
        }}

        .viewer-footer a:hover {{
            text-decoration: underline;
        }}

        .generated-by {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 6px;
            margin-bottom: 12px;
            font-size: 12px;
            color: var(--text-secondary);
        }}

        .generated-by a {{
            color: #28FF3A;
            text-decoration: none;
            font-weight: 500;
        }}

        .generated-by a:hover {{
            text-decoration: underline;
        }}

        .methodology-block {{
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 16px;
            padding: 8px 12px;
            background: #f8f9fa;
            border-radius: 4px;
        }}

        /* FAQ Styles - Hidden by default */
        .faq-section {{
            margin-top: 32px;
            padding-top: 24px;
            border-top: 1px solid #eee;
        }}

        .faq-section.collapsed .faq-content {{
            display: none;
        }}

        .faq-toggle {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            padding: 8px 0;
        }}

        .faq-toggle:hover .faq-title {{
            color: #28FF3A;
        }}

        .faq-toggle-icon {{
            font-size: 1.2rem;
            color: var(--text-secondary);
            transition: transform 0.2s ease;
        }}

        .faq-section:not(.collapsed) .faq-toggle-icon {{
            transform: rotate(180deg);
        }}

        .faq-content {{
            margin-top: 16px;
        }}

        .faq-title {{
            font-size: 1.25rem;
            margin: 0 0 16px 0;
        }}

        .faq-item {{
            margin-bottom: 12px;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
            background: #fff;
        }}

        .faq-question {{
            padding: 12px 16px;
            cursor: pointer;
            font-weight: 500;
            list-style: none;
        }}

        .faq-question::-webkit-details-marker {{
            display: none;
        }}

        .faq-question::before {{
            content: "+";
            margin-right: 10px;
            font-weight: bold;
        }}

        details[open] .faq-question::before {{
            content: "-";
        }}

        .faq-question:hover {{
            background: #f8f9fa;
        }}

        .faq-answer {{
            padding: 0 16px 12px 16px;
            color: var(--text-secondary);
            line-height: 1.6;
        }}

        @media (max-width: 768px) {{
            .viewer-container {{
                padding: 16px;
                margin: 10px;
            }}
            .viewer-title {{
                font-size: 1.4rem;
            }}
        }}

        /* ========================================
         * Interactive Table CSS (from 07-tables.css)
         * ======================================== */
        {table_css}
    </style>
</head>
<body>
    <div class="viewer-container">
        <div class="viewer-header">
            <h1 class="viewer-title">{escape_html(title)}</h1>
            <p class="viewer-subtitle">{escape_html(subtitle)}</p>
        </div>
        {methodology_html}

        <div class="generated-by">Generated by <a href="https://eliyahu.ai/hyperplexity" target="_blank" rel="noopener">Hyperplexity.AI</a></div>

        <div id="table-container">
            <!-- Table rendered by InteractiveTable.render() -->
        </div>

        {faq_html}

        <div class="viewer-footer">
            Generated by <a href="https://eliyahu.ai/hyperplexity" target="_blank">Hyperplexity</a> |
            <a href="https://eliyahu.ai/hyperplexity" target="_blank">Try Hyperplexity for your research</a>
        </div>
    </div>

    <script>
        // Embed table metadata
        window.TABLE_METADATA = {json.dumps(table_metadata)};
    </script>
    <script>
        /* ========================================
         * InteractiveTable Component (from 16-interactive-table.js)
         * Full featured: tooltips, highlighting, modal with sources
         * ======================================== */
        {table_js}
    </script>
    <script>
        // Render the table using InteractiveTable
        (function() {{
            var container = document.getElementById('table-container');
            var metadata = window.TABLE_METADATA;

            if (metadata && metadata.rows && metadata.columns) {{
                container.innerHTML = InteractiveTable.render(metadata, {{
                    showGeneralNotes: true,
                    showLegend: true
                }});
                InteractiveTable.init();
            }} else {{
                container.innerHTML = '<p style="color:#666;text-align:center;">Table data not available.</p>';
            }}
        }})();
    </script>
</body>
</html>'''

    return html


def main():
    """Generate all listicle pages."""
    # Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    json_path = os.path.join(base_dir, 'frontend', 'HyperplexityVsCompetition_20260130.json')
    output_dir = os.path.join(base_dir, 'frontend', 'seo', 'SEO_table_pages')

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Load table data
    print(f"Loading table data from: {json_path}")
    table_data = load_table_data(json_path)
    print(f"Loaded {len(table_data.get('rows', []))} rows, {len(table_data.get('columns', []))} columns")

    # Load CSS and JS assets once
    print("Loading CSS and JS assets...")
    table_css, table_js = load_assets(base_dir)
    print(f"  CSS: {len(table_css):,} bytes, JS: {len(table_js):,} bytes")

    # Generate each page
    last_updated = datetime.utcnow().strftime("%Y-%m-%d")

    for page_config in LISTICLE_PAGES:
        filename = page_config['filename']
        output_path = os.path.join(output_dir, filename)

        print(f"Generating: {filename}")

        # Create metadata with shuffled rows (different order per page)
        table_metadata = create_filtered_metadata(table_data, shuffle_seed=filename)

        # Generate HTML with full InteractiveTable component
        html = generate_html_with_interactive_table(
            table_metadata=table_metadata,
            title=page_config['title'],
            subtitle=page_config['subtitle'],
            description=page_config['description'],
            faqs=page_config['faqs'],
            last_updated=last_updated,
            table_css=table_css,
            table_js=table_js
        )

        # Write file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"  -> Wrote {len(html):,} bytes to {output_path}")

    print(f"\nGenerated {len(LISTICLE_PAGES)} HTML pages in: {output_dir}")


if __name__ == '__main__':
    main()
