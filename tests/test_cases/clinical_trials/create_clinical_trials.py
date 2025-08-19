import pandas as pd
import json
from datetime import datetime, timedelta
import random

# Clinical trials test data with real pharma companies as ID fields
data = {
    'Sponsor': [
        'Merck & Co.', 'Bristol Myers Squibb', 'Roche', 'AstraZeneca', 'Pfizer',
        'Novartis', 'Regeneron', 'GSK', 'Johnson & Johnson', 'Eli Lilly'
    ],
    'Drug_Name': [
        'Pembrolizumab', 'Nivolumab', 'Atezolizumab', 'Durvalumab', 'Avelumab',
        'Ipilimumab', 'Cemiplimab', 'Dostarlimab', 'Toripalimab', 'Sintilimab'
    ],
    'Trial_ID': [
        'NCT05234567', 'NCT05234568', 'NCT05234569', 'NCT05234570', 'NCT05234571',
        'NCT05234572', 'NCT05234573', 'NCT05234574', 'NCT05234575', 'NCT05234576'
    ],
    'Indication': [
        'Non-Small Cell Lung Cancer', 'Melanoma', 'Triple-Negative Breast Cancer', 
        'Bladder Cancer', 'Merkel Cell Carcinoma', 'Renal Cell Carcinoma',
        'Cutaneous Squamous Cell Carcinoma', 'Endometrial Cancer', 'Nasopharyngeal Carcinoma',
        'Hodgkin Lymphoma'
    ],
    'Phase': [
        'Phase 3', 'Phase 2', 'Phase 3', 'Phase 2/3', 'Phase 2',
        'Phase 3', 'Phase 2', 'Phase 3', 'Phase 2', 'Phase 2/3'
    ],
    'Primary_Endpoint': [
        'Overall Survival', 'Progression-Free Survival', 'Pathological Complete Response',
        'Overall Response Rate', 'Duration of Response', 'Overall Survival',
        'Objective Response Rate', 'Progression-Free Survival', 'Overall Response Rate',
        'Event-Free Survival'
    ],
    'Enrollment_Target': [450, 280, 520, 350, 180, 600, 220, 380, 150, 320],
    'Start_Date': [
        '2024-03-15', '2024-01-22', '2024-05-08', '2024-02-14', '2024-04-03',
        '2024-06-12', '2024-01-30', '2024-03-28', '2024-05-20', '2024-02-07'
    ]
}

# Create DataFrame
df = pd.DataFrame(data)

# Save to Excel
df.to_excel('clinical_trials.xlsx', index=False)

# Create column config with real companies as ID fields
config = {
    "general_notes": "This table tracks clinical trials for oncology immunotherapy drugs. The focus is on validating current trial status, sponsor information, and key endpoints for investment and research monitoring purposes.",
    "default_model": "sonar-pro",
    "default_search_context_size": "low",
    "validation_targets": [
        {
            "column": "Sponsor",
            "description": "Company or organization sponsoring the trial",
            "importance": "ID",
            "format": "String",
            "notes": "Use official company name - these are real pharma companies",
            "examples": ["Merck & Co.", "Bristol Myers Squibb", "Roche"],
            "search_group": 0
        },
        {
            "column": "Drug_Name",
            "description": "Name of the investigational drug or therapy",
            "importance": "ID",
            "format": "String", 
            "notes": "Use established drug names from known companies",
            "examples": ["Pembrolizumab", "Nivolumab", "Atezolizumab"],
            "search_group": 0
        },
        {
            "column": "Trial_ID",
            "description": "ClinicalTrials.gov identifier for the current/latest trial",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "Must find real NCT number through search - this will be validated",
            "examples": ["NCT05234567", "NCT05234568", "NCT05234569"],
            "search_group": 1,
            "search_context_size": "medium"
        },
        {
            "column": "Indication",
            "description": "Disease or condition being studied",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "Use specific cancer type or medical condition",
            "examples": ["Non-Small Cell Lung Cancer", "Melanoma", "Triple-Negative Breast Cancer"],
            "search_group": 1
        },
        {
            "column": "Phase",
            "description": "Clinical trial phase",
            "importance": "CRITICAL", 
            "format": "String",
            "notes": "Standard phase nomenclature (Phase 1, 2, 3, etc.)",
            "examples": ["Phase 3", "Phase 2", "Phase 2/3"],
            "search_group": 1
        },
        {
            "column": "Primary_Endpoint",
            "description": "Main outcome measure of the trial",
            "importance": "HIGH",
            "format": "String",
            "notes": "Primary efficacy or safety endpoint", 
            "examples": ["Overall Survival", "Progression-Free Survival", "Overall Response Rate"],
            "search_group": 2
        },
        {
            "column": "Enrollment_Target",
            "description": "Target number of patients to enroll",
            "importance": "MEDIUM",
            "format": "Number",
            "notes": "Integer value representing patient count",
            "examples": ["450", "280", "520"],
            "search_group": 3
        },
        {
            "column": "Start_Date",
            "description": "Date the trial started or is expected to start",
            "importance": "HIGH",
            "format": "Date",
            "notes": "Must be in YYYY-MM-DD format",
            "examples": ["2024-03-15", "2024-01-22", "2024-05-08"],
            "search_group": 3
        }
    ]
}

# Save config
with open('clinical_trials_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("Clinical trials test case created successfully!") 