import pandas as pd
import json

# Biotech research companies test data with real companies as ID fields
data = {
    'Company_Name': [
        'Moderna Inc.', 'BioNTech SE', 'Novavax Inc.', 'CureVac N.V.', 'Genmab A/S',
        'Seagen Inc.', 'Alexion Pharmaceuticals', 'Biogen Inc.', 'Vertex Pharmaceuticals', 'Regeneron Pharmaceuticals'
    ],
    'Ticker': [
        'MRNA', 'BNTX', 'NVAX', 'CVAC', 'GMAB',
        'SGEN', 'ALXN', 'BIIB', 'VRTX', 'REGN'
    ],
    'Focus_Area': [
        'mRNA Therapeutics', 'Cancer Immunotherapy', 'Protein-based Vaccines', 'mRNA Technology', 'Antibody Therapeutics',
        'Antibody-Drug Conjugates', 'Rare Disease Therapeutics', 'Neurological Disorders', 'Cystic Fibrosis', 'Monoclonal Antibodies'
    ],
    'Pipeline_Count': [
        45, 28, 12, 18, 35,
        22, 30, 41, 15, 38
    ],
    'Market_Cap_B': [
        42.8, 15.2, 3.4, 2.1, 7.8,
        18.5, 175.2, 33.4, 112.7, 68.9
    ],
    'R_D_Spend_M': [
        2847, 1245, 567, 423, 892,
        1567, 4231, 2456, 1834, 3021
    ],
    'Last_Earnings': [
        '2024-11-08', '2024-11-12', '2024-11-05', '2024-11-14', '2024-10-30',
        '2024-11-07', '2024-10-28', '2024-11-01', '2024-11-04', '2024-11-06'
    ]
}

# Create DataFrame
df = pd.DataFrame(data)

# Save to Excel
df.to_excel('biotech_research.xlsx', index=False)

# Create column config with real companies as ID fields
config = {
    "general_notes": "This table tracks biotech companies focusing on innovative therapeutics and drug development. The emphasis is on validating company information, pipeline data, financial metrics, and research focus areas for investment analysis and competitive intelligence.",
    "default_model": "sonar-pro",
    "default_search_context_size": "low",
    "validation_targets": [
        {
            "column": "Company_Name",
            "description": "Official registered name of the biotech company",
            "importance": "ID",
            "format": "String",
            "notes": "Full legal corporate name - these are real established biotech companies",
            "examples": ["Moderna Inc.", "BioNTech SE", "Novavax Inc."],
            "search_group": 0
        },
        {
            "column": "Ticker",
            "description": "Stock exchange ticker symbol",
            "importance": "ID",
            "format": "String",
            "notes": "Exchange trading symbol - real public company tickers",
            "examples": ["MRNA", "BNTX", "NVAX"],
            "search_group": 0
        },
        {
            "column": "Focus_Area",
            "description": "Primary therapeutic or technology focus",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "Main area of research and development",
            "examples": ["mRNA Therapeutics", "Cancer Immunotherapy", "Protein-based Vaccines"],
            "search_group": 1
        },
        {
            "column": "Pipeline_Count",
            "description": "Number of programs in development pipeline",
            "importance": "CRITICAL",
            "format": "Number",
            "notes": "Total count of therapeutic programs - will be validated through search",
            "examples": ["45", "28", "12"],
            "search_group": 2,
            "search_context_size": "medium"
        },
        {
            "column": "Market_Cap_B",
            "description": "Market capitalization in billions USD",
            "importance": "CRITICAL",
            "format": "Number",
            "notes": "Current market value in billions - will be validated",
            "examples": ["42.8", "15.2", "3.4"],
            "search_group": 2
        },
        {
            "column": "R_D_Spend_M",
            "description": "Annual R&D spending in millions USD",
            "importance": "HIGH",
            "format": "Number",
            "notes": "Research and development expenditure",
            "examples": ["2847", "1245", "567"],
            "search_group": 3,
            "preferred_model": "claude-sonnet-4-20250514"
        },
        {
            "column": "Last_Earnings",
            "description": "Date of most recent earnings report",
            "importance": "MEDIUM",
            "format": "Date",
            "notes": "Must be in YYYY-MM-DD format",
            "examples": ["2024-11-08", "2024-11-12", "2024-11-05"],
            "search_group": 3
        }
    ]
}

# Save config
with open('biotech_research_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("Biotech research test case created successfully!") 