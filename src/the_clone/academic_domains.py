#!/usr/bin/env python3
"""
Academic domain whitelist for scholarly searches.
"""

ACADEMIC_DOMAINS = [
    "scholar.google.com",
    "semanticscholar.org",
    "pubmed.ncbi.nlm.nih.gov",
    "europepmc.org",
    "jstor.org",
    "sciencedirect.com",
    "link.springer.com",
    "onlinelibrary.wiley.com",
    "tandfonline.com",
    "nature.com",
    "science.org",
    "cell.com",
    "pnas.org",
    "acm.org",
    "ieee.org",
    "doi.org",
    "crossref.org",
    "arxiv.org",
    "biorxiv.org",
    "medrxiv.org",
]


def get_academic_domains():
    """Get list of academic/scholarly domains."""
    return ACADEMIC_DOMAINS.copy()
