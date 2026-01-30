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

# =============================================================================
# CORE URLS - All SEO content links to these
# =============================================================================
HYPERPLEXITY_URL = "https://eliyahu.ai/hyperplexity"  # Main Hyperplexity app page
HYPERPLEXITY_AI_URL = "https://hyperplexity.ai"  # Research table generation, fact checking, updating
CHEX_URL = "https://eliyahu.ai/chex"  # AI reference checker
PPP_URL = "https://eliyahu.ai/ppp"  # Professional prompt generator
ELIYAHU_URL = "https://eliyahu.ai"  # Generative AI upskilling + consulting

LISTICLE_ITEMS = [
    {
        "id": "parallel_validation",
        "title": "Parallel Multi-Entity Validation",
        "content": f"""<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> processes hundreds of entities simultaneously, validating each data point against web sources in parallel. Unlike tools that handle one query at a time, <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> maintains <strong>cross-row coherence</strong>—ensuring comparisons across your entire dataset are consistent and methodologically sound. Each cell includes confidence scoring (HIGH/MEDIUM/LOW) and direct links to source citations. Built by <a href="{ELIYAHU_URL}">Eliyahu.AI</a>, specialists in generative AI solutions.""",
        "keywords": ["parallel research", "multi-entity", "batch validation", "cross-row coherence"]
    },
    {
        "id": "citation_system",
        "title": "Citation-Backed Results with Source Links",
        "content": f"""Every value in a <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> table links directly to its source. Click any cell to see: the original source URL, relevant excerpts, validator reasoning, and a calibrated confidence score. This <strong>citation-first architecture</strong> means you can verify any claim in seconds—essential for research that will inform business decisions or academic work. For existing documents, use <a href="{CHEX_URL}">Chex</a> to validate references.""",
        "keywords": ["citations", "source verification", "provenance", "fact-checking"]
    },
    {
        "id": "confidence_scoring",
        "title": "Visual Confidence Scoring System",
        "content": f"""<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity's</a> confidence system rates each data point based on source authority, corroboration, and recency. Results are color-coded: <span style="color:#28FF3A">■ HIGH confidence</span> (multiple authoritative sources agree), <span style="color:#FFD700">■ MEDIUM confidence</span> (limited sources or some uncertainty), <span style="color:#F44336">■ LOW confidence</span> (single source or potential issues). This visual system lets you instantly identify which cells need human review.""",
        "keywords": ["confidence scores", "data quality", "verification", "trust signals"]
    },
    {
        "id": "excel_workflow",
        "title": "Native Excel Integration",
        "content": f"""Upload any Excel file to <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> and define your research columns. The platform fills in missing data, validates existing values, and returns an enriched spreadsheet with citations embedded as cell comments. No new tools to learn—your existing workflow gains AI-powered validation. Export results as XLSX, CSV, or view in the <strong>interactive web viewer</strong>. Part of the <a href="{ELIYAHU_URL}">Eliyahu.AI</a> suite of generative AI tools.""",
        "keywords": ["Excel", "spreadsheet", "data enrichment", "export"]
    },
    {
        "id": "interactive_viewer",
        "title": "Interactive Research Table Viewer",
        "content": f"""The <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> viewer transforms data tables into explorable interfaces. Features include: <strong>column filtering</strong> by confidence level, <strong>expandable citations</strong> showing full source context, <strong>sortable columns</strong> for any dimension, and <strong>shareable links</strong> for team collaboration. No installation required—tables render in any modern browser.""",
        "keywords": ["data viewer", "interactive table", "visualization", "collaboration"]
    },
    {
        "id": "reference_checking",
        "title": "AI Reference Checking with Chex",
        "content": f"""<a href="{CHEX_URL}">Chex</a> is <a href="{ELIYAHU_URL}">Eliyahu.AI's</a> dedicated AI reference checker. Paste text containing citations, and <a href="{CHEX_URL}">Chex</a> verifies each claim against its cited source. Perfect for: <strong>fact-checking articles</strong>, <strong>validating AI-generated content</strong>, <strong>auditing research papers</strong>, and <strong>verifying competitor claims</strong>. Each reference receives an accuracy score with detailed explanations of any discrepancies. Complements <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity's</a> table generation capabilities.""",
        "keywords": ["reference checking", "citation verification", "fact-checking", "Chex"]
    },
    {
        "id": "pay_per_use",
        "title": "Pay-Per-Use Pricing (No Subscriptions)",
        "content": f"""<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> charges only for research performed—no monthly subscriptions, no per-seat licenses, no minimum commitments. Small projects cost pennies. Large competitive analyses remain affordable at scale. Pricing is transparent and predictable: you see estimated costs before starting any validation run. <strong>Free credits</strong> are available for new users to evaluate the platform.""",
        "keywords": ["pricing", "pay-per-use", "no subscription", "cost-effective"]
    },
    {
        "id": "free_preview",
        "title": "Free 3-Row Preview Before You Commit",
        "content": f"""Not sure if <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> is right for your research? The <strong>free preview mode</strong> validates your first 3 rows at no cost—just enter your email. See exactly how <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> handles your specific data before committing to a full validation run. Preview results include full citations and confidence scoring, so you can evaluate quality before spending credits. Also try <a href="{CHEX_URL}">Chex</a> for reference checking.""",
        "keywords": ["free preview", "try before buy", "3 rows free", "no risk"]
    },
    {
        "id": "dynamic_updates",
        "title": "Dynamic Table Refresh and Fact-Checking",
        "content": f"""Markets change constantly. <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> tables can be refreshed on demand—re-validating data against current sources while preserving your table structure. The built-in <strong>fact-checking engine</strong> flags stale data automatically. Keep competitive intelligence current without rebuilding tables from scratch. Version history tracks how data has changed over time.""",
        "keywords": ["refresh", "update", "dynamic data", "fact-checking", "version history"]
    },
    {
        "id": "domain_coverage",
        "title": "Domain-Wide Research Coverage",
        "content": f"""Most AI tools answer individual questions. <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> excels at <strong>systematic domain coverage</strong>: researching 50+ companies across 20+ dimensions, surveying entire market segments, or auditing complete product catalogs. Define entities and attributes once, and <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> ensures consistent, comparable data across your entire research scope. Need help designing your research? <a href="{ELIYAHU_URL}">Eliyahu.AI</a> offers generative AI consulting.""",
        "keywords": ["domain research", "market coverage", "systematic analysis", "scalable"]
    },
    {
        "id": "human_oversight",
        "title": "Built for Human Oversight",
        "content": f"""<a href="{HYPERPLEXITY_URL}">Hyperplexity</a> is designed to augment human judgment, not replace it. Every feature supports verification: <strong>confidence scores</strong> highlight uncertainty, <strong>citations</strong> enable source checking, <strong>preview mode</strong> validates approach before full runs. The EU AI Act (2025) requires human oversight for AI systems—<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> provides the transparency infrastructure to comply. <a href="{ELIYAHU_URL}">Eliyahu.AI</a> specializes in responsible AI implementation.""",
        "keywords": ["human oversight", "AI transparency", "verification", "EU AI Act"]
    },
    {
        "id": "ai_upskilling",
        "title": "Generative AI Training and Consulting",
        "content": f"""<a href="{ELIYAHU_URL}">Eliyahu.AI</a> provides enterprise generative AI upskilling and consulting services. Learn to leverage tools like <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> for research table generation, <a href="{CHEX_URL}">Chex</a> for reference validation, and <a href="{PPP_URL}">PPP</a> for professional prompts. From hands-on workshops to strategic consulting, <a href="{ELIYAHU_URL}">Eliyahu.AI</a> helps teams adopt AI responsibly and effectively.""",
        "keywords": ["AI training", "consulting", "upskilling", "generative AI", "enterprise"]
    },
    {
        "id": "prompt_generator",
        "title": "Professional Prompt Generator (PPP)",
        "content": f"""<a href="{PPP_URL}">PPP</a> is <a href="{ELIYAHU_URL}">Eliyahu.AI's</a> professional prompt generator—create optimized prompts for any AI task. Whether you're using <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> for research, ChatGPT for writing, or other AI tools, well-crafted prompts dramatically improve results. <a href="{PPP_URL}">PPP</a> helps you structure requests, include context, and get better outputs from any large language model.""",
        "keywords": ["prompt engineering", "prompt generator", "AI prompts", "LLM", "ChatGPT"]
    }
]


# =============================================================================
# COMPETITOR COMPARISON TEMPLATES
# =============================================================================

COMPARISON_SECTIONS = {
    "academic": {
        "title": "Academic Research Tools Comparison",
        "competitors": ["Elicit", "Consensus", "Scite", "SciSpace", "ResearchRabbit"],
        "hyperplexity_angle": f'While academic tools excel at literature search, <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> adds multi-entity validation with confidence scoring—ideal for systematic reviews and meta-analyses that require verified data tables.'
    },
    "general_ai": {
        "title": "General AI Assistants vs Specialized Research Tools",
        "competitors": ["ChatGPT", "Claude", "Gemini", "Perplexity"],
        "hyperplexity_angle": f'General AI assistants provide single-query answers. <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> structures research into validated tables with persistent citations—better for ongoing competitive intelligence and research projects.'
    },
    "data_platforms": {
        "title": "AI Data Platforms Comparison",
        "competitors": ["Parallel FindAll API", "Parallel Deep Research API", "AITable.ai"],
        "hyperplexity_angle": f'API-first platforms require development resources. <a href="{HYPERPLEXITY_URL}">Hyperplexity\'s</a> Excel interface and interactive viewer make validated research accessible to non-technical users while maintaining enterprise-grade accuracy.'
    }
}


# =============================================================================
# FAQ CONTENT - Comprehensive FAQs with links (visible on page, generates JSON-LD)
# =============================================================================

HYPERPLEXITY_FAQS = [
    # Core product questions
    {
        "question": "What is Hyperplexity?",
        "answer": f'<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> is an AI-powered research platform that generates validated data tables with citations. Unlike general AI assistants that answer one question at a time, <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> researches dozens or hundreds of entities in parallel—filling entire spreadsheets with fact-checked data. Every cell includes confidence scoring and links to source citations, so you can verify any claim instantly. Built by <a href="{ELIYAHU_URL}">Eliyahu.AI</a>.'
    },
    {
        "question": "How does Hyperplexity validate data?",
        "answer": f'<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> uses a multi-stage validation pipeline: (1) AI generates initial research from web sources, (2) a separate validation system checks each claim against primary sources, (3) confidence scores are assigned based on source authority and corroboration, (4) citations with URLs and excerpts are attached to every cell. The result is research you can trust—and verify yourself.'
    },
    {
        "question": "What are confidence scores in Hyperplexity?",
        "answer": f'<a href="{HYPERPLEXITY_URL}">Hyperplexity</a> rates each data point with a confidence level: <strong>HIGH</strong> (green) means multiple authoritative sources agree, <strong>MEDIUM</strong> (yellow) indicates limited sources or some uncertainty, <strong>LOW</strong> (red) flags single-source data or potential issues. This visual system helps you instantly identify which cells need human review, supporting responsible AI use and human oversight.'
    },
    # Pricing and trial
    {
        "question": "How much does Hyperplexity cost?",
        "answer": f'<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> uses transparent pay-per-use pricing—no monthly subscriptions, no per-seat licenses, no minimum commitments. You only pay for research actually performed. Small projects cost pennies; large competitive analyses remain affordable at scale. Estimated costs are shown before you start any validation run, so there are no surprises.'
    },
    {
        "question": "Can I try Hyperplexity for free?",
        "answer": f'Yes! <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> offers a free 3-row preview with just your email. Upload your spreadsheet, define your columns, and see exactly how <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> handles your specific data—complete with citations and confidence scores—before spending any credits. New users also receive free credits to evaluate the full platform.'
    },
    # Workflow and features
    {
        "question": "Does Hyperplexity work with Excel?",
        "answer": f'Absolutely. <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> is designed for Excel-based workflows. Upload any .xlsx or .csv file, define which columns need research, and <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> fills in the blanks. When validation completes, download your enriched spreadsheet with all citations embedded as cell comments. You can also view results in the interactive web viewer or export to multiple formats.'
    },
    {
        "question": "What is the Hyperplexity interactive viewer?",
        "answer": f'The <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> viewer transforms data tables into explorable web interfaces. Features include: filtering by confidence level, expandable cells showing full citations and source excerpts, sortable columns, and shareable links for team collaboration. Tables render in any modern browser with no installation required. You can share validated research with stakeholders via a simple URL.'
    },
    {
        "question": "Can Hyperplexity update existing tables?",
        "answer": f'Yes. <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> tables can be refreshed on demand—re-validating data against current web sources while preserving your table structure. This is ideal for competitive intelligence that needs to stay current. The system flags stale data automatically and tracks version history so you can see how information has changed over time.'
    },
    # Chex reference checker
    {
        "question": "What is Chex?",
        "answer": f'<a href="{CHEX_URL}">Chex</a> is <a href="{ELIYAHU_URL}">Eliyahu.AI\'s</a> dedicated AI reference checker. Paste any text containing citations, and <a href="{CHEX_URL}">Chex</a> verifies each claim against its cited source. It\'s perfect for fact-checking articles, validating AI-generated content, auditing research papers, or verifying competitor claims. Each reference receives an accuracy score with detailed explanations of any discrepancies found.'
    },
    {
        "question": "How is Chex different from Hyperplexity?",
        "answer": f'<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> generates new research tables with citations from scratch. <a href="{CHEX_URL}">Chex</a> validates existing documents—checking whether citations actually support the claims they\'re attached to. Use <a href="{HYPERPLEXITY_URL}">Hyperplexity</a> when you need to research and fill in data; use <a href="{CHEX_URL}">Chex</a> when you need to verify references in content you already have.'
    },
    # Use cases
    {
        "question": "What is Hyperplexity best for?",
        "answer": f'<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> excels at systematic research across many entities: competitive intelligence (comparing 50+ companies), market analysis (surveying industry segments), due diligence (validating claims across portfolios), academic research (literature review tables), and any project requiring consistent, comparable data with citations. It\'s built for research that needs to be trusted and verified.'
    },
    {
        "question": "Can Hyperplexity help with competitive intelligence?",
        "answer": f'<a href="{HYPERPLEXITY_URL}">Hyperplexity</a> was designed for competitive intelligence. Define your competitors and the dimensions you want to compare (pricing, features, market position, etc.), and <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> researches them all in parallel with consistent methodology. The result is a validated comparison matrix you can trust for strategic decisions—not a one-off AI answer you can\'t verify.'
    },
    # Technical and trust
    {
        "question": "How accurate is Hyperplexity?",
        "answer": f'<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> prioritizes transparency over false confidence. Every data point includes: the confidence level (HIGH/MEDIUM/LOW), direct links to source URLs, relevant excerpts from sources, and validator reasoning. This means you can verify any claim yourself. The system is designed for human oversight—you see exactly what the AI found and why it believes it\'s accurate.'
    },
    {
        "question": "Is Hyperplexity compliant with AI regulations?",
        "answer": f'<a href="{HYPERPLEXITY_URL}">Hyperplexity</a> is built for the EU AI Act (2025) era. The platform provides full transparency: confidence scores, source citations, validation reasoning, and audit trails. This supports human oversight requirements and responsible AI use. <a href="{ELIYAHU_URL}">Eliyahu.AI</a> specializes in helping organizations implement AI responsibly—contact us for enterprise compliance guidance.'
    },
    # Company and services
    {
        "question": "Who makes Hyperplexity?",
        "answer": f'<a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> and <a href="{CHEX_URL}">Chex</a> are built by <a href="{ELIYAHU_URL}">Eliyahu.AI</a>, a generative AI consultancy specializing in research automation and responsible AI implementation. We also offer <a href="{PPP_URL}">PPP</a> (Professional Prompt Generator) and enterprise AI training services. Our tools are designed for professionals who need AI they can trust and verify.'
    },
    {
        "question": "Does Eliyahu.AI offer consulting services?",
        "answer": f'Yes. <a href="{ELIYAHU_URL}">Eliyahu.AI</a> provides enterprise generative AI consulting and upskilling services. We help teams adopt AI tools like <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a>, <a href="{CHEX_URL}">Chex</a>, and <a href="{PPP_URL}">PPP</a> effectively, and we design custom AI solutions for research and data validation workflows. From hands-on workshops to strategic implementation, we help organizations use AI responsibly.'
    },
    {
        "question": "What is PPP?",
        "answer": f'<a href="{PPP_URL}">PPP</a> (Professional Prompt Generator) is <a href="{ELIYAHU_URL}">Eliyahu.AI\'s</a> tool for creating optimized prompts for any AI task. Whether you\'re using <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> for research, ChatGPT for writing, or Claude for analysis, well-crafted prompts dramatically improve results. <a href="{PPP_URL}">PPP</a> helps you structure requests, include context, and get better outputs from any large language model.'
    },
]


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

    def get_faqs(self, slug: str, count: int = 6) -> List[Dict[str, str]]:
        """
        Get rotated FAQs based on page slug.

        Args:
            slug: Page identifier for deterministic selection
            count: Number of FAQs to return (default 6 for good coverage)

        Returns:
            List of FAQ dicts with 'question' and 'answer' keys
        """
        seed = self.hash_string(slug)
        selected = []
        used_indices = set()

        # Always include first 3 core FAQs (What is, How validate, Pricing)
        # Then rotate the rest
        core_count = min(3, count)
        for i in range(core_count):
            selected.append(HYPERPLEXITY_FAQS[i])
            used_indices.add(i)

        # Fill remaining slots with rotated FAQs
        remaining = count - core_count
        for i in range(remaining):
            idx = (seed + i * 13 + 3) % len(HYPERPLEXITY_FAQS)  # Start after core FAQs
            attempts = 0
            while idx in used_indices and attempts < len(HYPERPLEXITY_FAQS):
                idx = (idx + 1) % len(HYPERPLEXITY_FAQS)
                attempts += 1
            if idx not in used_indices:
                used_indices.add(idx)
                selected.append(HYPERPLEXITY_FAQS[idx])

        return selected

    def get_all_faqs(self) -> List[Dict[str, str]]:
        """Get all FAQs (for JSON-LD schema)."""
        return HYPERPLEXITY_FAQS

    def render_seo_html(
        self,
        slug: str,
        include_header: bool = True,
        item_count: int = 5,
        comparison_count: int = 3,
        faq_count: int = 6
    ) -> str:
        """
        Render complete listicle-style SEO content as HTML.

        Args:
            slug: Page identifier for deterministic rotation
            include_header: Include H1/H2 headers
            item_count: Number of listicle items (features)
            comparison_count: Number of competitor comparisons
            faq_count: Number of FAQs to include (visible accordion)

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
            html_parts.append(f'''
<section class="seo-comparisons">
    <h2>How <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> Compares to Alternatives</h2>
    <div class="comparison-grid">
''')
            for comp in comparisons:
                website_link = f'<a href="{comp["website"]}" rel="nofollow">{comp["name"]}</a>' if comp.get('website') else comp['name']
                strengths_short = comp.get('strengths', '')[:200] + '...' if len(comp.get('strengths', '')) > 200 else comp.get('strengths', '')
                diff_short = comp.get('vs_hyperplexity', '')[:300] + '...' if len(comp.get('vs_hyperplexity', '')) > 300 else comp.get('vs_hyperplexity', '')

                html_parts.append(f'''
        <div class="comparison-card">
            <h3><a href="{HYPERPLEXITY_URL}">Hyperplexity</a> vs {website_link}</h3>
            <p><strong>{comp['name']} strengths:</strong> {strengths_short}</p>
            <p><strong>Key difference:</strong> {diff_short}</p>
            <p><strong>Pricing:</strong> {comp.get('pricing', 'See website')}</p>
        </div>
''')

            html_parts.append('</div></section>')

        # FAQ section (visible accordion - required by Google for FAQ rich snippets)
        faqs = self.get_faqs(slug, faq_count)
        if faqs:
            html_parts.append(f'''
<section class="seo-faq">
    <h2>Frequently Asked Questions About <a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a></h2>
    <div class="faq-list">
''')
            for faq in faqs:
                html_parts.append(f'''
        <details class="faq-item">
            <summary class="faq-question">{faq['question']}</summary>
            <div class="faq-answer">{faq['answer']}</div>
        </details>
''')
            html_parts.append('</div></section>')

        # CTA section with all product links
        html_parts.append(f'''
<section class="seo-cta">
    <h2>Try <a href="{ELIYAHU_URL}">Eliyahu.AI</a> Tools Free</h2>
    <p>Generate your first validated research table with free credits. No subscription required.</p>
    <ul class="seo-links">
        <li><a href="{HYPERPLEXITY_AI_URL}">Hyperplexity</a> – AI research table generation with citations</li>
        <li><a href="{HYPERPLEXITY_URL}">Hyperplexity App</a> – Start your validated research</li>
        <li><a href="{CHEX_URL}">Chex</a> – AI reference checker for documents</li>
        <li><a href="{PPP_URL}">PPP</a> – Professional prompt generator</li>
        <li><a href="{ELIYAHU_URL}">Eliyahu.AI</a> – Generative AI consulting &amp; upskilling</li>
    </ul>
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
