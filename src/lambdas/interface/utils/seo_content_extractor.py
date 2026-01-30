"""
SEO Content Extractor for Hyperplexity Static HTML

Extracts and generates SEO content blocks from competitive intelligence data.
Content is designed to be rotated/selected based on page slug for variety.

Key Hyperplexity Value Propositions:
- Fast parallel research
- Accurate with citations and confidence scoring
- Pay-per-use pricing (no subscriptions)
- Interactive Viewer + Excel frontend
- Built for human oversight
- Dynamic updating - keeps information fresh
- Best-in-class interactive data viewer
- Covers entire domains, not just single research questions
"""

import json
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# HERO STATEMENTS - Rotate based on page hash
# =============================================================================

HERO_STATEMENTS = [
    {
        "id": "speed",
        "headline": "Research at the Speed of Thought",
        "tagline": "Hyperplexity validates hundreds of data points in parallel - what takes hours manually happens in minutes.",
        "cta": "Generate your first validated table"
    },
    {
        "id": "accuracy",
        "headline": "Every Fact Cited. Every Claim Verified.",
        "tagline": "Hyperplexity doesn't just find information - it validates every cell with citations, confidence scores, and source links.",
        "cta": "See validation in action"
    },
    {
        "id": "pricing",
        "headline": "Pay Only for What You Use",
        "tagline": "No subscriptions. No seat licenses. Just straightforward pay-per-use pricing that scales with your research needs.",
        "cta": "Start with free credits"
    },
    {
        "id": "interface",
        "headline": "From Excel to Insight in One Click",
        "tagline": "Upload your spreadsheet, define your columns, and watch Hyperplexity fill in validated data with full citations.",
        "cta": "Try the Excel workflow"
    },
    {
        "id": "oversight",
        "headline": "AI Research You Can Actually Trust",
        "tagline": "Built for human oversight - every value shows its confidence level, sources, and reasoning so you stay in control.",
        "cta": "Explore the transparency features"
    },
    {
        "id": "refresh",
        "headline": "Keep Your Data Fresh, Automatically",
        "tagline": "Markets change. Competitors evolve. Hyperplexity makes updating your research tables as easy as clicking refresh.",
        "cta": "See dynamic updating"
    },
    {
        "id": "viewer",
        "headline": "The Most Powerful Research Table Viewer",
        "tagline": "Interactive filtering, expandable citations, confidence highlighting, and export options - all in one elegant interface.",
        "cta": "Explore a sample table"
    },
    {
        "id": "domain",
        "headline": "Cover Entire Markets, Not Just Questions",
        "tagline": "Research 50 companies across 20 dimensions simultaneously. Hyperplexity handles the breadth while maintaining depth.",
        "cta": "Build your competitive matrix"
    }
]


# =============================================================================
# FEATURE PARAGRAPHS - Longer content blocks for SEO
# =============================================================================

FEATURE_PARAGRAPHS = [
    {
        "id": "parallel_research",
        "title": "Parallel Multi-Entity Research",
        "content": "Traditional research tools force you to investigate one entity at a time. Hyperplexity revolutionizes this workflow by researching dozens or hundreds of entities simultaneously. Define your research dimensions once, and Hyperplexity applies them across your entire dataset - whether that's 10 companies or 1,000 clinical trials. Each cell is independently validated with citations, ensuring accuracy at scale without sacrificing depth."
    },
    {
        "id": "citation_system",
        "title": "Citation-Backed Validation",
        "content": "Every value in a Hyperplexity table comes with full provenance. Click any cell to see the exact sources, relevant excerpts, and confidence scoring that support the data. Unlike AI tools that generate plausible-sounding answers, Hyperplexity shows its work - making it easy to verify, audit, and trust the results. This citation-first approach is essential for research that matters."
    },
    {
        "id": "confidence_scoring",
        "title": "Confidence Scoring System",
        "content": "Not all information is equally reliable. Hyperplexity's confidence scoring system rates each data point based on source quality, corroboration across sources, and recency. High-confidence cells are highlighted in green, medium in yellow, and low in red - giving you instant visual feedback on where to focus your verification efforts. This human-oversight-first design keeps you in control."
    },
    {
        "id": "excel_integration",
        "title": "Seamless Excel Integration",
        "content": "Start with the spreadsheet you already have. Hyperplexity accepts Excel uploads directly - just define your columns and let the system fill in the blanks. When validation completes, download your enriched spreadsheet with all citations embedded in comments. No new tools to learn, no data migration required. Your existing workflow, supercharged with AI validation."
    },
    {
        "id": "interactive_viewer",
        "title": "Interactive Data Viewer",
        "content": "The Hyperplexity viewer transforms raw data into an explorable interface. Filter by confidence level, expand cells to see full citations, sort by any column, and drill into specific entities. The viewer works in your browser with no installation required, and tables can be shared via simple links. It's the fastest way to explore and present validated research."
    },
    {
        "id": "dynamic_updates",
        "title": "Dynamic Table Updates",
        "content": "Research doesn't end when you publish. Markets shift, companies pivot, and new information emerges daily. Hyperplexity tables can be refreshed on demand - updating stale data while preserving your structure and previous validations. Set confidence thresholds to flag cells that need re-verification, and keep your competitive intelligence current without starting from scratch."
    },
    {
        "id": "cost_efficiency",
        "title": "Cost-Efficient at Scale",
        "content": "Enterprise research tools charge per seat, per month, regardless of usage. Hyperplexity's pay-per-use model means you only pay for actual research performed. Small projects cost pennies. Large-scale competitive analyses remain affordable. No annual contracts, no minimum commitments - just transparent pricing that makes sense for research workflows that vary in intensity."
    },
    {
        "id": "domain_coverage",
        "title": "Domain-Wide Research Coverage",
        "content": "Most AI research tools answer single questions well. Hyperplexity excels at systematic coverage - mapping entire competitive landscapes, surveying complete market segments, or auditing full product catalogs. Define the entities, define the dimensions, and Hyperplexity ensures consistent, comparable data across your entire research domain."
    },
    {
        "id": "human_oversight",
        "title": "Designed for Human Oversight",
        "content": "AI should augment human judgment, not replace it. Every Hyperplexity feature is designed to keep humans in the loop. Confidence scores highlight uncertainty. Citations enable verification. The interactive viewer makes patterns visible. Preview mode lets you validate the approach before committing to full research. Trust is earned through transparency, and Hyperplexity provides the tools to verify every claim."
    },
    {
        "id": "chex_reference",
        "title": "Reference Checking with Chex",
        "content": "Hyperplexity's Chex feature validates references in existing documents. Paste text with citations, and Chex verifies each claim against the cited sources. Perfect for fact-checking articles, validating research papers, or auditing AI-generated content. Every reference is scored for accuracy, with detailed explanations of any discrepancies found."
    }
]


# =============================================================================
# COMPARISON TEMPLATES - For competitive positioning
# =============================================================================

COMPARISON_INTRO_TEMPLATES = [
    "When comparing {competitor} to Hyperplexity, the key differences emerge in {dimension}.",
    "While {competitor} excels at {strength}, Hyperplexity offers distinct advantages in {dimension}.",
    "{competitor} and Hyperplexity take different approaches to {dimension}.",
    "Researchers choosing between {competitor} and Hyperplexity should consider their needs for {dimension}."
]


class SEOContentExtractor:
    """
    Extracts and generates SEO content from competitive intelligence data.
    Uses deterministic selection based on page slug for consistent rotation.
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
                    'parallel_research': cells.get('Parallel Entity Research', {}).get('full_value', ''),
                    'cross_row_coherence': cells.get('Cross-Row Coherence', {}).get('full_value', ''),
                    'table_capabilities': cells.get('Research Table Capabilities', {}).get('full_value', ''),
                    'validation_features': cells.get('Validation/Fact-checking Features', {}).get('full_value', ''),
                    'key_strengths': cells.get('Key Strengths', {}).get('full_value', ''),
                    'pricing': cells.get('Pricing Model', {}).get('full_value', ''),
                    'best_use_case': cells.get('Best Use Case', {}).get('full_value', ''),
                    'vs_hyperplexity': cells.get('Key Differentiator vs. Hyperplexity', {}).get('full_value', ''),
                    'category': cells.get('Overall Category', {}).get('full_value', '')
                }

    @staticmethod
    def hash_string(s: str) -> int:
        """Deterministic FNV-1a hash for content rotation."""
        h = 2166136261
        for char in s:
            h = h ^ ord(char)
            h = (h * 16777619) & 0xFFFFFFFF
        return h

    def get_hero(self, slug: str, offset: int = 0) -> Dict[str, str]:
        """
        Get a hero statement based on page slug.

        Args:
            slug: Page identifier for deterministic selection
            offset: Offset for selecting different hero with same slug

        Returns:
            Hero dict with headline, tagline, cta
        """
        seed = self.hash_string(slug)
        idx = (seed + offset) % len(HERO_STATEMENTS)
        return HERO_STATEMENTS[idx]

    def get_paragraphs(self, slug: str, count: int = 3) -> List[Dict[str, str]]:
        """
        Get feature paragraphs based on page slug.

        Args:
            slug: Page identifier for deterministic selection
            count: Number of paragraphs to return

        Returns:
            List of paragraph dicts with title and content
        """
        seed = self.hash_string(slug)
        selected = []

        for i in range(count):
            idx = (seed + i * 7) % len(FEATURE_PARAGRAPHS)  # Use prime offset
            para = FEATURE_PARAGRAPHS[idx]
            if para not in selected:
                selected.append(para)

        return selected

    def get_competitor_comparison(self, competitor_name: str) -> Optional[Dict[str, Any]]:
        """
        Get comparison data for a specific competitor.

        Args:
            competitor_name: Name of competitor to compare against

        Returns:
            Comparison dict or None if competitor not found
        """
        comp = self._competitor_cache.get(competitor_name.lower())
        if not comp:
            return None

        return {
            'competitor': comp['name'],
            'their_strength': comp['key_strengths'],
            'vs_hyperplexity': comp['vs_hyperplexity'],
            'their_category': comp['category'],
            'hyperplexity_advantage': self._derive_advantage(comp)
        }

    def _derive_advantage(self, competitor: Dict) -> str:
        """Derive Hyperplexity's advantage based on competitor weaknesses."""
        advantages = []

        if competitor.get('parallel_research', '').lower() in ['no', 'limited']:
            advantages.append("parallel multi-entity research")
        if competitor.get('cross_row_coherence', '').lower() in ['no', 'limited']:
            advantages.append("cross-row coherence for consistent comparisons")
        if 'subscription' in competitor.get('pricing', '').lower():
            advantages.append("flexible pay-per-use pricing")
        if competitor.get('validation_features', '').lower() in ['no', 'limited', 'none']:
            advantages.append("citation-backed validation with confidence scoring")

        if advantages:
            return "Hyperplexity offers " + ", ".join(advantages)
        return "Hyperplexity provides unique advantages in parallel research validation"

    def get_rotated_comparisons(self, slug: str, count: int = 2) -> List[Dict[str, Any]]:
        """
        Get rotated competitor comparisons based on slug.

        Args:
            slug: Page identifier for deterministic selection
            count: Number of comparisons to include

        Returns:
            List of comparison dicts
        """
        if not self._competitor_cache:
            return []

        seed = self.hash_string(slug)
        competitors = list(self._competitor_cache.keys())
        selected = []

        for i in range(count):
            idx = (seed + i * 11) % len(competitors)  # Prime offset
            comp_name = competitors[idx]
            comparison = self.get_competitor_comparison(comp_name)
            if comparison and comparison not in selected:
                selected.append(comparison)

        return selected

    def get_category_competitors(self, category: str) -> List[str]:
        """Get list of competitors in a specific category."""
        return [
            comp['name'] for comp in self._competitor_cache.values()
            if category.lower() in comp.get('category', '').lower()
        ]

    def generate_seo_block(
        self,
        slug: str,
        include_hero: bool = True,
        paragraph_count: int = 3,
        comparison_count: int = 2
    ) -> Dict[str, Any]:
        """
        Generate a complete SEO content block for a page.

        Args:
            slug: Page identifier for deterministic rotation
            include_hero: Whether to include hero statement
            paragraph_count: Number of feature paragraphs
            comparison_count: Number of competitor comparisons

        Returns:
            Complete SEO block with all content
        """
        block = {
            'slug': slug,
            'seed': self.hash_string(slug)
        }

        if include_hero:
            block['hero'] = self.get_hero(slug)

        block['paragraphs'] = self.get_paragraphs(slug, paragraph_count)

        if self.competitive_data:
            block['comparisons'] = self.get_rotated_comparisons(slug, comparison_count)
            block['general_context'] = self.competitive_data.get('general_notes', '')

        return block

    def render_seo_html(
        self,
        slug: str,
        include_hero: bool = True,
        paragraph_count: int = 3,
        comparison_count: int = 2
    ) -> str:
        """
        Render SEO content as HTML string.

        Args:
            slug: Page identifier
            include_hero: Include hero section
            paragraph_count: Number of paragraphs
            comparison_count: Number of comparisons

        Returns:
            HTML string for embedding
        """
        block = self.generate_seo_block(slug, include_hero, paragraph_count, comparison_count)
        html_parts = []

        # Hero section
        if 'hero' in block:
            hero = block['hero']
            html_parts.append(f'''
            <div class="seo-hero">
                <h2>{self._escape(hero['headline'])}</h2>
                <p class="seo-tagline">{self._escape(hero['tagline'])}</p>
            </div>
            ''')

        # Feature paragraphs
        for para in block.get('paragraphs', []):
            html_parts.append(f'''
            <div class="seo-feature">
                <h3>{self._escape(para['title'])}</h3>
                <p>{self._escape(para['content'])}</p>
            </div>
            ''')

        # Competitor comparisons
        for comp in block.get('comparisons', []):
            html_parts.append(f'''
            <div class="seo-comparison">
                <h3>Hyperplexity vs {self._escape(comp['competitor'])}</h3>
                <p><strong>{self._escape(comp['competitor'])}</strong>: {self._escape(comp['their_strength'][:300] if comp['their_strength'] else '')}</p>
                <p><strong>Key Difference</strong>: {self._escape(comp['vs_hyperplexity'][:400] if comp['vs_hyperplexity'] else '')}</p>
                <p>{self._escape(comp['hyperplexity_advantage'])}</p>
            </div>
            ''')

        # General context
        if block.get('general_context'):
            html_parts.append(f'''
            <div class="seo-context">
                <p>{self._escape(block['general_context'][:500])}</p>
            </div>
            ''')

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
