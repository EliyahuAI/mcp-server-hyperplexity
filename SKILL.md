---
name: hyperplexity
version: 1.0.0
description: >
  Generate, validate, and fact-check research tables using Hyperplexity AI.
  Use this skill to: (1) create a research table from a natural language prompt
  with AI-sourced, citation-backed data; (2) validate and enrich an existing
  Excel or CSV file with per-cell confidence scores, corrections, and citations;
  (3) fact-check claims and citations in any text against authoritative sources.
  Free $20 credit for new accounts at hyperplexity.ai/account.
author: Hyperplexity
homepage: https://hyperplexity.ai
license: MIT
requires:
  env:
    HYPERPLEXITY_API_KEY:
      description: >
        API key from hyperplexity.ai/account.
        New accounts get $20 free — no credit card required to start.
      required: true
install:
  command: uvx
  args: ["mcp-server-hyperplexity"]
mcp:
  transport: stdio
tags: [data, validation, research, fact-check, excel, csv, ai, citations, enrichment]
---

# Hyperplexity Skill

This skill connects your agent to the Hyperplexity AI research and validation platform.

## What this enables

- **Generate research tables**: Describe the table you want in natural language; AI builds and validates it row by row with citations and confidence scores
- **Validate existing tables**: Upload Excel or CSV files; every cell is checked against authoritative sources and returned with corrections, explanations, and supporting citations
- **Fact-check text**: Submit any text or document; claims and citations are verified against live authoritative data

## Setup

1. Get your API key at [hyperplexity.ai/account](https://hyperplexity.ai/account) — new accounts get $20 free
2. Add `HYPERPLEXITY_API_KEY` to your environment
3. Install: tell your agent *"Install the hyperplexity skill"*

## Example prompts

- *"Create a table of the top 15 AI chip companies with columns: company, HQ, latest chip, founded year, market cap"*
- *"Validate my companies.xlsx — check website, headcount, and funding round for every row"*
- *"Fact-check this analyst report: [paste text]"*
- *"Re-run validation on my corrected table from last week's job"*
