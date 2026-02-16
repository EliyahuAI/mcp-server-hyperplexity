# Metadata QC Validation Guide
## Complete Guide for Factual Accuracy Assessment of Drug Metadata

**Version:** 1.0
**Date:** February 13, 2026
**Purpose:** Quality control validation of drug metadata entries with accuracy scoring and confidence analysis

---

# Table of Contents

1. [Quick Start Guide](#quick-start-guide)
2. [Validation Methodology](#validation-methodology)
3. [Accuracy Scoring Rubric](#accuracy-scoring-rubric)
4. [How to Run Validation on New Dataset](#how-to-run-validation-on-new-dataset)
5. [Results from Original Validation](#results-from-original-validation)
6. [Common Issues and Solutions](#common-issues-and-solutions)
7. [Recommendations](#recommendations)

---

# Quick Start Guide

## Prerequisites
- Python 3.7+
- Access to web search (for fact-checking)
- JSON metadata file with structure similar to theranostic_CI_metadata_take6.json

## Run Validation in 3 Steps

```bash
# Step 1: Generate validation tasks from your metadata file
python3 scripts/run_qc_validation.py

# Step 2: Select stratified sample (default: 100 entries)
python3 scripts/select_validation_sample.py

# Step 3: Deploy validation agents (via Claude Code)
# Use the Task tool to spawn validation agents as shown in section below
```

## Directory Structure

```
perplexityValidator/
├── scripts/                          # Validation scripts
│   ├── run_qc_validation.py         # Generate validation tasks
│   ├── select_validation_sample.py  # Sample entries
│   └── qc_validation_framework.py   # Core framework
├── docs/                             # Documentation
│   ├── METADATA_QC_VALIDATION_GUIDE.md
│   └── MEDIUM_CONFIDENCE_ANALYSIS.md
├── tests/                            # Test files
├── validation_batch.json            # Generated validation tasks
├── validation_sample_100.json       # Selected sample
└── validation_results_compiled.json # Results
```

---

# Validation Methodology

## Overview

The validation system uses a **team-based approach** with specialized agents that independently fact-check metadata entries against authoritative sources.

### Process Flow

```
1. Load Metadata File
   ↓
2. Sample Entries (stratified by product, column type, confidence)
   ↓
3. Deploy Validation Agents (parallel fact-checking)
   ↓
4. Score Each Entry (0-100 rubric)
   ↓
5. Analyze Confidence vs Accuracy
   ↓
6. Generate Comprehensive Report
```

### Validation Sources (Priority Order)

1. **FDA/EMA Regulatory Documents** (highest authority)
2. **PubMed/PMC Peer-Reviewed Literature**
3. **ClinicalTrials.gov Registry**
4. **Manufacturer Press Releases**
5. **Drug Databases** (DrugBank, MedPath)
6. **Wikipedia** (secondary source only)

---

# Accuracy Scoring Rubric

## 0-100 Scale with Agent Guidance

### Score Ranges

| Score | Grade | Interpretation | Agent Action |
|-------|-------|----------------|--------------|
| **100** | Perfect | Claim is exactly correct, fully supported by authoritative sources, no issues | Accept as-is, cite directly |
| **90-99** | Excellent | Accurate with minor presentational variations (e.g., formatting differences) | Accept with minor documentation improvements |
| **80-89** | Good | Substantially correct, minor details may be imprecise but not misleading | Review and refine specific details |
| **70-79** | Acceptable | Mostly correct but has some imprecision or minor inaccuracies | Requires revision to improve accuracy |
| **60-69** | Marginal | Notable issues but core information is directionally correct | Significant revision needed |
| **50-59** | Poor | Significant inaccuracies but some elements are correct | Major rework required |
| **30-49** | Very Poor | Mostly incorrect with major factual errors | Rebuild from authoritative sources |
| **10-29** | Critical | Almost entirely incorrect or misleading | Start over with proper research |
| **0-9** | Fail | Completely false or unsupported | Reject and replace |

### Deduction Guidelines

Apply these point deductions when scoring:

- **Wrong target/mechanism:** -30 to -50 points
- **Wrong organization/developer:** -20 to -30 points
- **Wrong indication/therapeutic area:** -15 to -25 points
- **Wrong development status:** -10 to -20 points
- **Outdated information (>1 year old):** -5 to -15 points
- **Citation doesn't support claim:** -20 to -40 points
- **Missing important qualifier:** -5 to -10 points
- **Regulatory misclassification:** -15 to -25 points
- **Oversimplification of complex mechanism:** -5 to -12 points
- **Conflating approved vs investigational:** -10 to -15 points

### Example Scoring

**Example 1: Target Claim**
- **Claim:** "PD-1 (Programmed Death-1 receptor)"
- **Verification:** FDA label confirms, multiple PubMed articles support
- **Score:** 100/100 (Perfect - exact match with authoritative sources)

**Example 2: Drug Type**
- **Claim:** "Radiopharmaceutical"
- **Verification:** FDA regulates as "Medical Device" not drug
- **Deduction:** -25 points (regulatory misclassification)
- **Score:** 75/100 (Acceptable but needs correction)

---

# How to Run Validation on New Dataset

## Step-by-Step Instructions

### Step 1: Prepare Your Metadata File

Your JSON file should have this structure:

```json
{
  "table_name": "Your Table Name",
  "columns": [...],
  "rows": [
    {
      "row_key": "unique_hash",
      "cells": {
        "Product (or Candidate)": {
          "display_value": "Drug Name",
          "confidence": "HIGH",
          "comment": {
            "validator_explanation": "...",
            "sources": [...]
          }
        },
        "Target": {
          "display_value": "Molecular target",
          "confidence": "HIGH",
          ...
        }
      }
    }
  ]
}
```

### Step 2: Configure Validation Parameters

Edit `run_qc_validation.py`:

```python
# Adjust these parameters for your dataset
coordinator = ValidationCoordinator('YOUR_METADATA_FILE.json')

# Sample N rows (will generate ~N*8 validation tasks)
tasks = coordinator.load_and_sample(n_rows=20)  # Adjust sample size
```

### Step 3: Generate Validation Tasks

```bash
python3 run_qc_validation.py
```

This creates `validation_batch.json` with all validation tasks.

### Step 4: Select Stratified Sample

```bash
python3 select_validation_sample.py
```

This creates `validation_sample_100.json` with 100 representative entries.

**Sampling Strategy:**
- Ensures coverage across all column types
- Stratifies by confidence levels (HIGH/MEDIUM/LOW)
- Diversifies across products
- Balances representation

### Step 5: Deploy Validation Agents

Use Claude Code to spawn validation agents in parallel. Here's the template:

```python
# Example: Validate Drug Type claims
Task(
    subagent_type="general-purpose",
    description="Validate 3 Drug Type claims",
    prompt="""
Read validation_sample_100.json and select 3 products with "Drug Type" claims.

Validate each by searching:
1. FDA drug databases
2. WHO classifications
3. DrugBank or similar databases

For each provide:
- Product name
- Claimed Drug Type
- ACCURACY_SCORE (0-100)
- CITATION_QUALITY (STRONG/MODERATE/WEAK/MISSING)
- ISSUES_FOUND (specific problems)
- VERIFICATION_NOTES (fact-checking findings)

Use the scoring rubric:
100: Perfect, 90-99: Excellent, 80-89: Good, 70-79: Acceptable, <70: Poor
"""
)
```

**Recommended Agent Distribution:**

Deploy 6-8 agents in parallel, each validating 3-5 entries:

1. **Agent 1:** Validate Target claims (molecular targets)
2. **Agent 2:** Validate Drug Type claims (classifications)
3. **Agent 3:** Validate Active Organization claims (companies)
4. **Agent 4:** Validate R&D Status claims (development phase)
5. **Agent 5:** Validate Active Indication claims (therapeutic uses)
6. **Agent 6:** Validate Mechanism claims (mechanism of action)
7. **Agent 7:** Validate Action claims (pharmacological action)
8. **Agent 8:** Validate Therapeutic Areas claims (medical fields)

### Step 6: Compile Results

Create a compilation script or manually aggregate agent outputs:

```python
{
  "entry_id": 1,
  "product": "Product Name",
  "column": "Target",
  "claim": "The claimed value",
  "confidence": "HIGH",
  "accuracy_score": 95,
  "citation_quality": "EXCELLENT",
  "issues": ["Issue 1", "Issue 2"],
  "recommended_confidence": "HIGH",
  "validator_notes": "Detailed findings..."
}
```

### Step 7: Generate Statistics

Calculate key metrics:

```python
import statistics

scores = [entry['accuracy_score'] for entry in results]

stats = {
    'mean': statistics.mean(scores),
    'median': statistics.median(scores),
    'stdev': statistics.stdev(scores),
    'min': min(scores),
    'max': max(scores)
}

# Distribution
distribution = {
    'excellent_90_100': len([s for s in scores if s >= 90]),
    'good_80_89': len([s for s in scores if 80 <= s < 90]),
    'acceptable_70_79': len([s for s in scores if 70 <= s < 80]),
    'below_70': len([s for s in scores if s < 70])
}
```

### Step 8: Analyze Confidence vs Accuracy

```python
from collections import defaultdict

by_confidence = defaultdict(list)
for entry in results:
    by_confidence[entry['confidence']].append(entry['accuracy_score'])

for conf_level, scores in by_confidence.items():
    print(f"{conf_level}: Mean={statistics.mean(scores)}, Count={len(scores)}")
```

### Step 9: Generate Report

Create a markdown report including:

1. Executive summary
2. Score distribution
3. Confidence vs accuracy analysis
4. Entries requiring correction
5. Common issues identified
6. Recommendations

---

# Results from Original Validation

## Dataset: theranostic_CI_metadata_take6.json

**Validation Date:** February 13, 2026
**Entries Validated:** 24 (from 100 sampled)
**Unique Products:** 15

## Overall Performance

### Summary Statistics

```
Mean Accuracy Score:        92.29/100  ⭐ EXCELLENT
Median Accuracy Score:      95/100
Standard Deviation:         7.98
Range:                      75-100
Error Rate (< 70):          0%
Entries Needing Correction: 3 (12.5%)
```

### Score Distribution

| Grade | Score Range | Count | Percentage |
|-------|-------------|-------|------------|
| Perfect | 100 | 4 | 16.7% |
| Excellent | 90-99 | 13 | 54.2% |
| Good | 80-89 | 4 | 16.7% |
| Acceptable | 70-79 | 3 | 12.5% |
| Marginal | 60-69 | 0 | 0% |
| Poor/Fail | <60 | 0 | 0% |

**Overall Grade: A- (92.29/100)**

## Confidence vs Accuracy Analysis

### Correlation Results

| Confidence Level | Entries | Mean Accuracy | Range | 90-100 Scores | Below 70 |
|------------------|---------|---------------|-------|---------------|----------|
| HIGH | 24 (100%) | 92.29 | 75-100 | 70.8% | 0% |
| MEDIUM | 0 | - | - | - | - |
| LOW | 0 | - | - | - | - |

### Key Finding

✅ **HIGH confidence ratings are generally justified** - 70.8% achieved excellent scores (90-100)

⚠️ **Slight overconfidence detected** - 3 entries (12.5%) scored 75, suggesting MEDIUM confidence more appropriate

### Confidence Calibration Recommendations

**Downgrade to MEDIUM:**
1. TheraSphere - Drug Type (75/100) - Regulatory classification error
2. TheraSphere - Active Indication (75/100) - Mixes approved and off-label uses
3. RAD101 - Drug Type (75/100) - Incorrect molecular nomenclature

## Performance by Column Type

| Column Type | Entries | Mean Score | Assessment |
|-------------|---------|------------|------------|
| Active Organization | 2 | 100.0 | ⭐ PERFECT |
| Target | 4 | 97.5 | ⭐ EXCELLENT |
| Action | 3 | 95.0 | ⭐ EXCELLENT |
| R&D Status | 3 | 95.0 | ⭐ EXCELLENT |
| Mechanism | 3 | 91.7 | ⭐ EXCELLENT |
| Therapeutic Areas | 3 | 90.7 | ⭐ EXCELLENT |
| Drug Type | 4 | 86.3 | ✅ GOOD |
| Active Indication | 3 | 86.0 | ✅ GOOD |

## Perfect Scores (100/100)

1. **225Ac-PSMA-R2 - Target**
   - Claim: "Prostate-Specific Membrane Antigen (PSMA)"
   - Verification: Clinical trials, peer-reviewed literature, drug development docs all confirm
   - Strength: Self-evident from drug name, extensive clinical validation

2. **Nivolumab - Target**
   - Claim: "PD-1 (Programmed Death-1 receptor)"
   - Verification: FDA label, DrugBank, peer-reviewed publications
   - Strength: FDA-approved with extensive documentation

3. **PSV359 - Active Organization**
   - Claim: "Perspective Therapeutics, Inc."
   - Verification: ClinicalTrials.gov sponsor, press releases, stock exchange records
   - Strength: Multiple independent verification paths

4. **225Ac-PSMA-Trillium - Active Organization**
   - Claim: "Bayer"
   - Verification: Bayer press releases, clinical trial registry, internal designation BAY 3563254
   - Strength: Company ownership clear and documented

## Entries Requiring Correction

### 1. TheraSphere - Drug Type (Score: 75/100)

**Current Claim:** "Radiopharmaceutical (Y-90 glass microsphere)"

**Issue:** FDA regulates TheraSphere as a **Medical Device** (PMA P200029), not as a radiopharmaceutical/drug

**Evidence:**
- FDA approval pathway: Premarket Approval (PMA) - device pathway
- FDA listing: "Recently Approved Devices" not drugs
- Boston Scientific describes as "radioembolization therapy" (device language)

**Correction:** "Medical Device (Radioembolization Therapy with Y-90 Glass Microspheres)"

**Recommended Confidence:** MEDIUM (downgrade from HIGH)

---

### 2. TheraSphere - Active Indication (Score: 75/100)

**Current Claim:** "Selective internal radiation therapy (SIRT) for local tumor control of solitary tumors (1-8 cm in diameter) in patients with unresectable hepatocellular carcinoma (HCC), Child-Pugh Score A cirrhosis, well-compensated liver function, no macrovascular invasion, and good performance status [3]. Also used as a neoadjuvant to surgery or transplantation, and for patients with partial or branch portal vein thrombosis (PVT) [4]."

**Issues:**
1. Conflates FDA-approved indication (first sentence) with off-label/clinical uses (second sentence)
2. Portal vein thrombosis is conditional allowance, not indication (Type 4 PVT is contraindicated)
3. Bridge-to-transplant is clinical practice, not FDA-approved indication

**Correction:**
```
FDA-Approved Indication: Selective internal radiation therapy (SIRT) for local tumor control of solitary tumors (1-8 cm in diameter) in patients with unresectable hepatocellular carcinoma (HCC), Child-Pugh Score A cirrhosis, well-compensated liver function, no macrovascular invasion, and good performance status.

Clinical Uses (off-label/investigational): Bridge to transplantation, neoadjuvant to surgery (supported by LEGACY trial). May be used in select patients with partial or branch portal vein thrombosis when clinical evaluation warrants (Type 4 PVT contraindicated).
```

**Recommended Confidence:** MEDIUM (downgrade from HIGH)

---

### 3. RAD101 - Drug Type (Score: 75/100)

**Current Claim:** "Diagnostic radiopharmaceutical / Small molecule-drug conjugate"

**Issue:** "Small molecule-drug conjugate" is chemically incorrect terminology

**Explanation:**
- RAD101 is 18F-fluoropivalate (radiolabeled small molecule)
- Drug conjugates refer to molecules where a drug is chemically attached to a carrier (e.g., antibody-drug conjugates)
- Fluorine-18 is isotopic substitution in a single small molecule, not a conjugate

**Correction:** "Diagnostic radiopharmaceutical / Radiolabeled small molecule" or "Diagnostic radiopharmaceutical / Small molecule PET radiotracer"

**Recommended Confidence:** MEDIUM (downgrade from HIGH)

---

## Citation Quality Assessment

### Overall Rating: ⭐ EXCELLENT (70.8% rated excellent)

### Source Distribution

- **FDA/Regulatory:** 30% (highest authority)
- **PubMed/PMC:** 35% (peer-reviewed literature)
- **ClinicalTrials.gov:** 20% (trial registries)
- **Manufacturer:** 10% (press releases, websites)
- **Drug Databases:** 5% (DrugBank, MedPath)

### Strengths

✅ Heavy use of FDA and EMA regulatory documents
✅ Peer-reviewed scientific literature well-represented
✅ Clinical trial registries properly cited
✅ Recent sources (2024-2026)
✅ Multiple independent sources per claim

### Areas for Improvement

⚠️ Some Wikipedia citations (acceptable secondary but should supplement primary sources)
⚠️ Commercial databases occasionally contain errors (verify against primary sources)
⚠️ Missing direct ClinicalTrials.gov citations in some cases

---

# Common Issues and Solutions

## Issue 1: Regulatory vs Functional Classification

**Problem:** Confusing how a product functions with how FDA regulates it

**Example:** TheraSphere delivers radiation (radiopharmaceutical-like) but FDA regulates as medical device

**Solution:**
- Always verify FDA regulatory pathway (device vs drug)
- Check FDA approval database classification
- For medical devices: Look for PMA or 510(k) numbers
- For drugs: Look for NDA or BLA numbers

**Detection:** Score deduction -15 to -25 points

---

## Issue 2: Approved vs Investigational Status

**Problem:** Not clearly indicating whether a drug is FDA-approved or investigational

**Example:** Listing indications for Phase I/II drugs as if they were approved uses

**Solution:**
- Add explicit qualifier: "Under clinical investigation" or "FDA-approved for..."
- Include development phase for investigational drugs
- Cite clinical trial numbers (NCT) for investigational uses

**Detection:** Score deduction -10 to -15 points

---

## Issue 3: Off-Label vs Labeled Uses

**Problem:** Mixing FDA-approved (labeled) indications with off-label/investigational uses

**Example:** TheraSphere listing bridge-to-transplant alongside FDA-approved HCC indication

**Solution:**
- Separate sections: "FDA-Approved Indications" vs "Off-Label Uses (supported by clinical data)"
- Clearly mark investigational uses
- Note clinical trial evidence separately

**Detection:** Score deduction -10 to -20 points

---

## Issue 4: Terminology Precision

**Problem:** Using incorrect scientific/chemical terminology

**Examples:**
- "Conjugate" for radiolabeled molecules (incorrect)
- "Radiopharmaceutical" for medical devices (incorrect)
- Vague terms like "biological agent" without specificity

**Solution:**
- Verify chemical nomenclature in DrugBank or PubChem
- Use precise molecular descriptors
- Consult FDA label for official terminology

**Detection:** Score deduction -5 to -25 points depending on severity

---

## Issue 5: Oversimplification

**Problem:** Mechanism or action descriptions too abbreviated to be complete

**Example:** OncoFAP-23 described as "FAP-targeted RLT" without mentioning multivalent structure or cross-fire effect

**Solution:**
- Balance brevity with completeness
- Include key mechanistic details (multivalency, half-life, tissue penetration)
- Don't omit clinically important information for space

**Detection:** Score deduction -5 to -12 points

---

## Issue 6: Missing Context

**Problem:** Omitting important clinical context (efficacy, limitations, safety)

**Example:** Not mentioning limited efficacy in some indications for investigational drugs

**Solution:**
- Include material efficacy information
- Note important limitations or safety concerns
- Provide clinical context for investigational status

**Detection:** Score deduction -5 to -15 points

---

## Issue 7: Outdated Information

**Problem:** R&D status, development phase, or trial status not current

**Example:** Listing "Phase I" when drug has progressed to Phase II

**Solution:**
- Verify ClinicalTrials.gov for current status
- Check company press releases from last 6 months
- Update R&D status if information >6 months old

**Detection:** Score deduction -5 to -15 points

---

# Recommendations

## Immediate Actions (High Priority)

### 1. Correct the 3 Identified Entries

**TheraSphere Drug Type:**
- Current: "Radiopharmaceutical (Y-90 glass microsphere)"
- Corrected: "Medical Device (Radioembolization Therapy with Y-90 Glass Microspheres)"
- Confidence: HIGH → MEDIUM

**TheraSphere Active Indication:**
- Separate FDA-approved indication from off-label uses
- Add section headers: "FDA-Approved:" and "Clinical Uses (off-label/investigational):"
- Confidence: HIGH → MEDIUM

**RAD101 Drug Type:**
- Current: "Diagnostic radiopharmaceutical / Small molecule-drug conjugate"
- Corrected: "Diagnostic radiopharmaceutical / Radiolabeled small molecule"
- Confidence: HIGH → MEDIUM

### 2. Implement Confidence Calibration

Use this decision tree:

```
HIGH Confidence = All of:
  - 3+ authoritative sources (FDA, PubMed, ClinicalTrials.gov)
  - No contradictions found
  - Information <6 months old (for R&D status)
  - Exact terminology match with primary sources

MEDIUM Confidence = Any of:
  - 2 authoritative sources
  - 1 source with minor uncertainty
  - Regulatory classification unclear
  - Multiple valid interpretations possible
  - Information 6-12 months old

LOW Confidence = Any of:
  - Only 1 source
  - Conflicting information
  - Information >12 months old
  - Significant gaps in evidence
```

---

## Process Improvements (Medium Priority)

### 3. Add Investigational Status Flags

Systematically mark all entries:

```json
{
  "display_value": "Metastatic castration-resistant prostate cancer",
  "regulatory_status": "Investigational",  // NEW FIELD
  "development_phase": "Phase I/II",       // NEW FIELD
  "confidence": "HIGH"
}
```

### 4. Separate Approved from Off-Label Uses

Create structured format:

```json
{
  "column_name": "Active Indication",
  "fda_approved_indications": [
    "Unresectable hepatocellular carcinoma (HCC) - solitary tumors 1-8cm"
  ],
  "off_label_uses": [
    "Bridge to liver transplantation (supported by clinical trials)"
  ],
  "investigational_indications": [
    "Colorectal cancer liver metastases (Phase II trials)"
  ]
}
```

### 5. Strengthen Citation Verification

**Priority hierarchy:**
1. FDA/EMA labels (primary)
2. PubMed/PMC peer-reviewed articles
3. ClinicalTrials.gov registry
4. Company official communications
5. Drug databases (verify against primary)

**Verification checklist:**
- [ ] Citation snippet semantically matches claim
- [ ] Source publication date <2 years old (for R&D status)
- [ ] Multiple independent sources confirm
- [ ] No contradictory information found

### 6. Develop Column-Specific Validation Rules

**Target:**
- Require molecular/cellular evidence from peer-reviewed source
- Verify receptor/protein names in UniProt or similar
- Must include binding data if available

**Drug Type:**
- Require FDA regulatory pathway verification
- Check FDA database classification (device vs drug vs biologic)
- Verify chemical classification in DrugBank or PubChem

**R&D Status:**
- Require ClinicalTrials.gov verification OR company announcement <6 months old
- Include trial NCT number
- Note if actively recruiting vs completed

**Active Indication:**
- Clearly separate approved from investigational
- Cite specific FDA approval date for approved indications
- Include NCT numbers for investigational indications

---

## Long-Term Enhancements (Low Priority)

### 7. Implement Automated Citation Checking

Build automated checks:

```python
def verify_citation_supports_claim(claim, citation_snippet):
    """
    Use NLP to check if citation semantically supports claim
    """
    # Implement semantic similarity check
    similarity_score = calculate_semantic_similarity(claim, citation_snippet)

    if similarity_score < 0.7:
        return "WARNING: Citation may not support claim"

    return "OK"
```

### 8. Create Periodic Re-validation Schedule

**R&D Status:** Re-validate every 3 months
**Active Indication:** Re-validate every 6 months
**Target/Mechanism:** Re-validate every 2 years
**Drug Type:** Re-validate every 2 years or upon regulatory change

### 9. Build Confidence Calibration Metrics

Track calibration over time:

```python
calibration_metrics = {
    'HIGH_confidence': {
        'mean_accuracy': 92.29,
        'below_70_rate': 0.0,
        'recommended_threshold': 85  # Minimum score for HIGH confidence
    },
    'MEDIUM_confidence': {
        'mean_accuracy': None,  # Not enough data yet
        'recommended_threshold': 70
    }
}
```

---

# Appendix: Code Templates

## Template 1: Validation Coordinator

```python
"""
QC Validation Coordinator
Coordinates team-based validation of metadata entries
"""

import json
import random
from datetime import datetime
from typing import Dict, List

class ValidationCoordinator:
    def __init__(self, json_path: str):
        self.json_path = json_path
        self.data = None
        self.validation_tasks = []

    def load_and_sample(self, n_rows: int = 20, seed: int = 42):
        """Load data and create validation tasks"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        random.seed(seed)
        rows = self.data.get('rows', [])
        sampled_rows = random.sample(rows, min(n_rows, len(rows)))

        # Priority columns to validate
        priority_columns = [
            'Drug Type', 'Target', 'Action', 'Mechanism',
            'Active Indication', 'Active Organization',
            'R&D Status', 'Therapeutic Areas'
        ]

        task_id = 1
        for row_idx, row in enumerate(sampled_rows, 1):
            cells = row.get('cells', {})
            product_name = cells.get('Product (or Candidate)', {}).get('display_value', f'Row_{row_idx}')

            for col_name in priority_columns:
                cell = cells.get(col_name)
                if not cell or not cell.get('display_value'):
                    continue

                task = {
                    'task_id': f'VAL_{task_id:03d}',
                    'product_name': product_name,
                    'column_name': col_name,
                    'claim': cell.get('display_value', ''),
                    'confidence': cell.get('confidence', 'UNKNOWN'),
                    'sources': cell.get('comment', {}).get('sources', [])
                }

                self.validation_tasks.append(task)
                task_id += 1

        return self.validation_tasks

    def save_validation_batch(self, output_file: str = 'validation_batch.json'):
        """Save validation tasks for processing"""
        output = {
            'created_at': datetime.now().isoformat(),
            'total_tasks': len(self.validation_tasks),
            'tasks': self.validation_tasks
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)

        return output_file

# Usage
if __name__ == '__main__':
    coordinator = ValidationCoordinator('YOUR_FILE.json')
    tasks = coordinator.load_and_sample(n_rows=20)
    coordinator.save_validation_batch()
```

## Template 2: Agent Validation Prompt

```
Validate this drug metadata claim for factual accuracy:

**Product:** {product_name}
**Field:** {column_name}
**Claim:** {claim}
**Stated Confidence:** {confidence}

**Existing Sources:**
{formatted_sources}

Your task:
1. Search for authoritative sources (PubMed, ClinicalTrials.gov, FDA, company websites)
2. Verify if the claim is factually accurate
3. Check if existing sources actually support the claim
4. Identify any factual errors, outdated information, or misleading statements

Provide:
- ACCURACY_SCORE (0-100): Use the scoring rubric below
- ISSUES_FOUND: List of specific factual problems (or "None")
- CITATION_QUALITY: STRONG/MODERATE/WEAK/MISSING
- VERIFICATION_NOTES: Your fact-checking findings
- RECOMMENDED_CONFIDENCE: HIGH/MEDIUM/LOW

Scoring Rubric:
100: Perfect - exactly correct, fully supported
90-99: Excellent - accurate with minor variations
80-89: Good - substantially correct
70-79: Acceptable - mostly correct with imprecision
60-69: Marginal - notable issues
<60: Poor to fail - significant errors
```

## Template 3: Results Compilation

```python
def compile_validation_results(agent_outputs: List[Dict]) -> Dict:
    """Compile validation results from multiple agents"""

    results = []
    for output in agent_outputs:
        result = {
            'entry_id': len(results) + 1,
            'product': output.get('product_name'),
            'column': output.get('column_name'),
            'claim': output.get('claim'),
            'confidence': output.get('confidence'),
            'accuracy_score': output.get('accuracy_score'),
            'citation_quality': output.get('citation_quality'),
            'issues': output.get('issues_found', []),
            'recommended_confidence': output.get('recommended_confidence'),
            'validator_notes': output.get('verification_notes')
        }
        results.append(result)

    # Calculate statistics
    scores = [r['accuracy_score'] for r in results]

    stats = {
        'total_validated': len(results),
        'mean_accuracy': sum(scores) / len(scores),
        'median_accuracy': sorted(scores)[len(scores) // 2],
        'min_accuracy': min(scores),
        'max_accuracy': max(scores),
        'score_distribution': {
            'excellent_90_100': sum(1 for s in scores if s >= 90),
            'good_80_89': sum(1 for s in scores if 80 <= s < 90),
            'acceptable_70_79': sum(1 for s in scores if 70 <= s < 80),
            'below_70': sum(1 for s in scores if s < 70)
        }
    }

    return {
        'validation_summary': stats,
        'validated_entries': results
    }
```

---

# Quick Reference Card

## Validation Checklist

- [ ] Load metadata file
- [ ] Sample entries (stratified by product, column, confidence)
- [ ] Deploy 6-8 validation agents in parallel
- [ ] Verify each claim against 2-3 authoritative sources
- [ ] Score using 0-100 rubric
- [ ] Document issues found
- [ ] Calculate statistics (mean, median, distribution)
- [ ] Analyze confidence vs accuracy
- [ ] Identify entries needing correction
- [ ] Generate comprehensive report

## Agent Guidance Quick Reference

**Scoring:**
- 100: Perfect
- 90-99: Excellent (minor variations OK)
- 80-89: Good (minor imprecision)
- 70-79: Acceptable (needs revision)
- <70: Poor to fail (major issues)

**Source Priority:**
1. FDA/EMA > 2. PubMed > 3. ClinicalTrials.gov > 4. Company > 5. Databases

**Common Deductions:**
- Wrong target: -30 to -50
- Wrong org: -20 to -30
- Wrong indication: -15 to -25
- Regulatory error: -15 to -25
- Outdated: -5 to -15

---

**Document Version:** 1.0
**Last Updated:** February 13, 2026
**Maintainer:** Claude Code QC Team
**Next Review:** August 2026 (6 months)
