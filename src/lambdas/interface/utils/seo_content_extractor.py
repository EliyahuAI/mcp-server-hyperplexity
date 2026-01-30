"""
SEO Content Extractor for Hyperplexity Static HTML

Generates listicle-style SEO content with rotating headers optimized for search:
- "Best AI Research Tools 2025"
- "Top Fact-Checking Software"
- "Best Competitive Intelligence Platforms"
etc.

Content includes actual links, citations, and rich comparisons from competitive data.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# =============================================================================
# LISTICLE HEADERS - 10 SEO-optimized rotating headers
# =============================================================================

LISTICLE_HEADERS = [
    {
        "id": "research_tools",
        "h1": "Best AI Research Tools for Data Validation (2025)",
        "h2": "Top Tools for Automated Research Tables with Citations",
        "intro": "Finding reliable data at scale requires tools that go beyond simple search. The best AI research tools validate information, provide citations, and maintain consistency across large datasets. Here's how the leading platforms compare."
    },
    {
        "id": "fact_checking",
        "h1": "Best Fact-Checking Software for Researchers",
        "h2": "AI-Powered Verification Tools That Show Their Sources",
        "intro": "In an era of AI-generated content and misinformation, fact-checking software has become essential. The best tools don't just verify claims—they provide transparent citations and confidence scores so you can trust the results."
    },
    {
        "id": "competitive_intel",
        "h1": "Top Competitive Intelligence Platforms (2025 Comparison)",
        "h2": "Best Tools for Market Research and Competitor Analysis",
        "intro": "Competitive intelligence requires systematic data collection across dozens or hundreds of entities. The best platforms automate this research while maintaining accuracy through validation and source verification."
    },
    {
        "id": "research_tables",
        "h1": "Best AI Tools for Creating Research Tables",
        "h2": "Automated Data Tables with Built-In Citation Tracking",
        "intro": "Research tables are only as good as the data they contain. Modern AI tools can generate comprehensive tables automatically, but the best ones validate every cell and link back to primary sources."
    },
    {
        "id": "citation_tools",
        "h1": "Best Citation and Source Verification Tools",
        "h2": "Software That Validates Claims Against Original Sources",
        "intro": "Whether you're writing a research paper, verifying AI output, or auditing a competitor's claims, citation tools help ensure accuracy. The best platforms trace every fact back to its source."
    },
    {
        "id": "data_validation",
        "h1": "Top AI Data Validation Tools for Business Research",
        "h2": "Platforms That Verify Information Before You Use It",
        "intro": "Bad data leads to bad decisions. AI data validation tools check information against multiple sources, flag uncertainties, and provide the confidence scores you need to act with certainty."
    },
    {
        "id": "market_research",
        "h1": "Best AI Market Research Tools (2025 Guide)",
        "h2": "Automated Platforms for Industry Analysis and Trends",
        "intro": "Market research at scale traditionally required large teams and months of work. AI-powered tools now automate data collection and validation, delivering research tables in hours instead of weeks."
    },
    {
        "id": "excel_research",
        "h1": "Best AI Tools for Excel-Based Research",
        "h2": "Spreadsheet Add-Ins and Platforms for Data Enrichment",
        "intro": "Most business research still lives in Excel. The best AI research tools integrate seamlessly with spreadsheets, enriching your existing data with validated information and embedded citations."
    },
    {
        "id": "reference_checker",
        "h1": "Best Reference Checking Software for Documents",
        "h2": "Tools That Verify Citations in Papers and Reports",
        "intro": "Reference checking is critical for academic papers, reports, and AI-generated content. The best tools automatically verify that citations support the claims they're attached to."
    },
    {
        "id": "enterprise_research",
        "h1": "Top Enterprise Research Platforms (2025)",
        "h2": "Scalable AI Tools for Large-Scale Data Validation",
        "intro": "Enterprise research requires platforms that scale—handling thousands of entities while maintaining validation quality. Here's how the leading enterprise research tools compare."
    }
]


# =============================================================================
# LISTICLE ITEMS - Rich content with links for each value proposition
# =============================================================================

HYPERPLEXITY_URL = "https://eliyahu.ai/hyperplexity"
CHEX_URL = "https://eliyahu.ai/hyperplexity?mode=chex"

LISTICLE_ITEMS = [
    {
        "id": "parallel_validation",
        "title": "Parallel Multi-Entity Validation",
        "content": f"""<a href="{HYPERPLEXITY_URL}">Hyperplexity</a> processes hundreds of entities simultaneously, validating each data point against web sources in parallel. Unlike tools that handle one query at a time, Hyperplexity maintains <strong>cross-row coherence</strong>—ensuring that comparisons across your entire dataset are consistent and methodologically sound. Each cell includes confidence scoring (HIGH/MEDIUM/LOW) and direct links to source citations.""",
        "keywords": ["parallel research", "multi-entity", "batch validation", "cross-row coherence"]
    },
    {
        "id": "citation_system",
        "title": "Citation-Backed Results with Source Links",
        "content": f"""Every value in a <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> table links directly to its source. Click any cell to see: the original source URL, relevant excerpts, validator reasoning, and a calibrated confidence score. This <strong>citation-first architecture</strong> means you can verify any claim in seconds—essential for research that will inform business decisions or academic work.""",
        "keywords": ["citations", "source verification", "provenance", "fact-checking"]
    },
    {
        "id": "confidence_scoring",
        "title": "Visual Confidence Scoring System",
        "content": f"""<a href="{HYPERPLEXITY_URL}">Hyperplexity's</a> confidence system rates each data point based on source authority, corroboration, and recency. Results are color-coded: <span style="color:#28FF3A">■ HIGH confidence</span> (multiple authoritative sources agree), <span style="color:#FFD700">■ MEDIUM confidence</span> (limited sources or some uncertainty), <span style="color:#F44336">■ LOW confidence</span> (single source or potential issues). This visual system lets you instantly identify which cells need human review.""",
        "keywords": ["confidence scores", "data quality", "verification", "trust signals"]
    },
    {
        "id": "excel_workflow",
        "title": "Native Excel Integration",
        "content": f"""Upload any Excel file to <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> and define your research columns. The platform fills in missing data, validates existing values, and returns an enriched spreadsheet with citations embedded as cell comments. No new tools to learn—your existing workflow gains AI-powered validation. Export results as XLSX, CSV, or view in the <strong>interactive web viewer</strong>.""",
        "keywords": ["Excel", "spreadsheet", "data enrichment", "export"]
    },
    {
        "id": "interactive_viewer",
        "title": "Interactive Research Table Viewer",
        "content": f"""The <a href="{HYPERPLEXITY_URL}">Hyperplexity viewer</a> transforms data tables into explorable interfaces. Features include: <strong>column filtering</strong> by confidence level, <strong>expandable citations</strong> showing full source context, <strong>sortable columns</strong> for any dimension, and <strong>shareable links</strong> for team collaboration. No installation required—tables render in any modern browser.""",
        "keywords": ["data viewer", "interactive table", "visualization", "collaboration"]
    },
    {
        "id": "reference_checking",
        "title": "Reference Checking with Chex",
        "content": f"""<a href="{CHEX_URL}">Hyperplexity Chex</a> validates citations in existing documents. Paste text containing references, and Chex verifies each claim against its cited source. Perfect for: <strong>fact-checking articles</strong>, <strong>validating AI-generated content</strong>, <strong>auditing research papers</strong>, and <strong>verifying competitor claims</strong>. Each reference receives an accuracy score with detailed explanations of any discrepancies.""",
        "keywords": ["reference checking", "citation verification", "fact-checking", "Chex"]
    },
    {
        "id": "pay_per_use",
        "title": "Pay-Per-Use Pricing (No Subscriptions)",
        "content": f"""<a href="{HYPERPLEXITY_URL}">Hyperplexity</a> charges only for research performed—no monthly subscriptions, no per-seat licenses, no minimum commitments. Small projects cost pennies. Large competitive analyses remain affordable at scale. Pricing is transparent and predictable: you see estimated costs before starting any validation run. <strong>Free credits</strong> are available for new users to evaluate the platform.""",
        "keywords": ["pricing", "pay-per-use", "no subscription", "cost-effective"]
    },
    {
        "id": "free_preview",
        "title": "Free 3-Row Preview Before You Commit",
        "content": f"""Not sure if <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> is right for your research? The <strong>free preview mode</strong> validates your first 3 rows at no cost—just enter your email. See exactly how the platform handles your specific data before committing to a full validation run. Preview results include full citations and confidence scoring, so you can evaluate quality before spending credits.""",
        "keywords": ["free preview", "try before buy", "3 rows free", "no risk"]
    },
    {
        "id": "dynamic_updates",
        "title": "Dynamic Table Refresh",
        "content": f"""Markets change constantly. <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> tables can be refreshed on demand—re-validating data against current sources while preserving your table structure. Set confidence thresholds to automatically flag stale data. Keep competitive intelligence current without rebuilding tables from scratch. Version history tracks how data has changed over time.""",
        "keywords": ["refresh", "update", "dynamic data", "version history"]
    },
    {
        "id": "domain_coverage",
        "title": "Domain-Wide Research Coverage",
        "content": f"""Most AI tools answer individual questions. <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> excels at <strong>systematic domain coverage</strong>: researching 50+ companies across 20+ dimensions, surveying entire market segments, or auditing complete product catalogs. Define entities and attributes once, and Hyperplexity ensures consistent, comparable data across your entire research scope.""",
        "keywords": ["domain research", "market coverage", "systematic analysis", "scalable"]
    },
    {
        "id": "human_oversight",
        "title": "Built for Human Oversight",
        "content": f"""<a href="{HYPERPLEXITY_URL}">Hyperplexity</a> is designed to augment human judgment, not replace it. Every feature supports verification: <strong>confidence scores</strong> highlight uncertainty, <strong>citations</strong> enable source checking, <strong>preview mode</strong> validates approach before full runs. The EU AI Act (2025) requires human oversight for AI systems—Hyperplexity provides the transparency infrastructure to comply.""",
        "keywords": ["human oversight", "AI transparency", "verification", "EU AI Act"]
    }
]


# =============================================================================
# COMPETITOR COMPARISON TEMPLATES
# =============================================================================

COMPARISON_SECTIONS = {
    "academic": {
        "title": "Academic Research Tools Comparison",
        "competitors": ["Elicit", "Consensus", "Scite", "SciSpace", "ResearchRabbit"],
        "hyperplexity_angle": "While academic tools excel at literature search, Hyperplexity adds multi-entity validation with confidence scoring—ideal for systematic reviews and meta-analyses that require verified data tables."
    },
    "general_ai": {
        "title": "General AI Assistants vs Specialized Research Tools",
        "competitors": ["ChatGPT", "Claude", "Gemini", "Perplexity"],
        "hyperplexity_angle": "General AI assistants provide single-query answers. Hyperplexity structures research into validated tables with persistent citations—better for ongoing competitive intelligence and research projects."
    },
    "data_platforms": {
        "title": "AI Data Platforms Comparison",
        "competitors": ["Parallel FindAll API", "Parallel Deep Research API", "AITable.ai"],
        "hyperplexity_angle": "API-first platforms require development resources. Hyperplexity's Excel interface and interactive viewer make validated research accessible to non-technical users while maintaining enterprise-grade accuracy."
    }
}


class SEOContentExtractor:
    """
    Generates listicle-style SEO content with rotating headers and rich linked content.
    Uses competitive intelligence data for comparison sections.
    """

    def __init__(self, competitive_data: Optional[Dict[str, Any]] = None):
        """
        Initialize with optional competitive intelligence data.

        Args:
            competitive_data: Parsed JSON from HyperplexityVsCompetition file
        """
        self.competitive_data = competitive_data
        self._competitor_cache = {}

        if competitive_data:
            self._build_competitor_cache()

    def _build_competitor_cache(self):
        """Build lookup cache for competitor data."""
        if not self.competitive_data:
            return

        for row in self.competitive_data.get('rows', []):
            cells = row.get('cells', {})
            name = cells.get('Tool/Platform Name', {}).get('display_value', '')
            if name:
                self._competitor_cache[name.lower()] = {
                    'name': name,
                    'website': cells.get('Website', {}).get('display_value', ''),
                    'primary_function': cells.get('Primary Function', {}).get('full_value', ''),
                    'key_strengths': cells.get('Key Strengths', {}).get('full_value', ''),
                    'vs_hyperplexity': cells.get('Key Differentiator vs. Hyperplexity', {}).get('full_value', ''),
                    'category': cells.get('Overall Category', {}).get('full_value', ''),
                    'pricing': cells.get('Pricing Model', {}).get('full_value', ''),
                    'validation_features': cells.get('Validation/Fact-checking Features', {}).get('full_value', '')
                }

    @staticmethod
    def hash_string(s: str) -> int:
        """Deterministic FNV-1a hash for content rotation."""
        h = 2166136261
        for char in s:
            h = h ^ ord(char)
            h = (h * 16777619) & 0xFFFFFFFF
        return h

    def get_listicle_header(self, slug: str) -> Dict[str, str]:
        """Get a listicle header based on page slug."""
        seed = self.hash_string(slug)
        idx = seed % len(LISTICLE_HEADERS)
        return LISTICLE_HEADERS[idx]

    def get_listicle_items(self, slug: str, count: int = 5) -> List[Dict[str, Any]]:
        """Get listicle items based on page slug, ensuring variety."""
        seed = self.hash_string(slug)
        selected = []
        used_indices = set()

        for i in range(count):
            # Use prime multiplier for better distribution
            idx = (seed + i * 7) % len(LISTICLE_ITEMS)
            attempts = 0
            while idx in used_indices and attempts < len(LISTICLE_ITEMS):
                idx = (idx + 1) % len(LISTICLE_ITEMS)
                attempts += 1
            used_indices.add(idx)
            selected.append(LISTICLE_ITEMS[idx])

        return selected

    def get_competitor_comparison(self, competitor_name: str) -> Optional[Dict[str, Any]]:
        """Get rich comparison data for a specific competitor."""
        comp = self._competitor_cache.get(competitor_name.lower())
        if not comp:
            return None

        return {
            'name': comp['name'],
            'website': comp['website'],
            'strengths': comp['key_strengths'],
            'vs_hyperplexity': comp['vs_hyperplexity'],
            'category': comp['category'],
            'pricing': comp['pricing']
        }

    def get_rotated_comparisons(self, slug: str, count: int = 3) -> List[Dict[str, Any]]:
        """Get rotated competitor comparisons based on slug."""
        if not self._competitor_cache:
            return []

        seed = self.hash_string(slug)
        competitors = list(self._competitor_cache.keys())
        selected = []
        used_indices = set()

        for i in range(count):
            idx = (seed + i * 11) % len(competitors)
            attempts = 0
            while idx in used_indices and attempts < len(competitors):
                idx = (idx + 1) % len(competitors)
                attempts += 1
            used_indices.add(idx)

            comp_name = competitors[idx]
            comparison = self.get_competitor_comparison(comp_name)
            if comparison:
                selected.append(comparison)

        return selected

    def render_seo_html(
        self,
        slug: str,
        include_header: bool = True,
        item_count: int = 5,
        comparison_count: int = 3
    ) -> str:
        """
        Render complete listicle-style SEO content as HTML.

        Args:
            slug: Page identifier for deterministic rotation
            include_header: Include H1/H2 headers
            item_count: Number of listicle items (features)
            comparison_count: Number of competitor comparisons

        Returns:
            HTML string with rich linked content
        """
        html_parts = []
        year = datetime.now().year

        # Header section
        if include_header:
            header = self.get_listicle_header(slug)
            html_parts.append(f'''
<article class="seo-listicle">
    <header class="seo-header">
        <h1>{header['h1']}</h1>
        <h2>{header['h2']}</h2>
        <p class="seo-intro">{header['intro']}</p>
        <p class="seo-updated">Last updated: {datetime.now().strftime('%B %Y')}</p>
    </header>
''')

        # Listicle items (numbered list)
        items = self.get_listicle_items(slug, item_count)
        html_parts.append('<section class="seo-features"><ol class="seo-list">')

        for i, item in enumerate(items, 1):
            html_parts.append(f'''
    <li class="seo-list-item" id="{item['id']}">
        <h3>{i}. {item['title']}</h3>
        <p>{item['content']}</p>
    </li>
''')

        html_parts.append('</ol></section>')

        # Competitor comparison section
        comparisons = self.get_rotated_comparisons(slug, comparison_count)
        if comparisons:
            html_parts.append('''
<section class="seo-comparisons">
    <h2>How Hyperplexity Compares to Alternatives</h2>
    <div class="comparison-grid">
''')
            for comp in comparisons:
                website_link = f'<a href="{comp["website"]}" rel="nofollow">{comp["name"]}</a>' if comp.get('website') else comp['name']
                strengths_short = comp.get('strengths', '')[:200] + '...' if len(comp.get('strengths', '')) > 200 else comp.get('strengths', '')
                diff_short = comp.get('vs_hyperplexity', '')[:300] + '...' if len(comp.get('vs_hyperplexity', '')) > 300 else comp.get('vs_hyperplexity', '')

                html_parts.append(f'''
        <div class="comparison-card">
            <h3>Hyperplexity vs {website_link}</h3>
            <p><strong>{comp['name']} strengths:</strong> {strengths_short}</p>
            <p><strong>Key difference:</strong> {diff_short}</p>
            <p><strong>Pricing:</strong> {comp.get('pricing', 'See website')}</p>
        </div>
''')

            html_parts.append('</div></section>')

        # CTA section
        html_parts.append(f'''
<section class="seo-cta">
    <h2>Try Hyperplexity Free</h2>
    <p>Generate your first validated research table with free credits. No subscription required.</p>
    <p><a href="{HYPERPLEXITY_URL}">Start Free at Hyperplexity</a> | <a href="{CHEX_URL}">Try Reference Checking with Chex</a></p>
</section>
''')

        # Close article
        if include_header:
            html_parts.append('</article>')

        return '\n'.join(html_parts)

    @staticmethod
    def _escape(text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ''
        return (str(text)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


def load_competitive_data(json_path: str) -> Optional[Dict[str, Any]]:
    """Load competitive intelligence JSON from file path."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[SEO] Could not load competitive data from {json_path}: {e}")
        return None


def load_competitive_data_from_s3(s3_client, bucket: str, key: str) -> Optional[Dict[str, Any]]:
    """Load competitive intelligence JSON from S3."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.warning(f"[SEO] Could not load competitive data from s3://{bucket}/{key}: {e}")
        return None
