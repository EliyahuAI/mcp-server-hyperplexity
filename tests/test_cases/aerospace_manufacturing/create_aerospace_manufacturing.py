import pandas as pd
import json

# Aerospace manufacturing suppliers test data with real companies as ID fields
data = {
    'Company_Name': [
        'Boeing Company', 'Airbus SE', 'Lockheed Martin', 'Northrop Grumman', 'Raytheon Technologies',
        'General Dynamics', 'Honeywell Aerospace', 'Rolls-Royce Holdings', 'Safran SA', 'L3Harris Technologies'
    ],
    'Headquarters': [
        'Chicago, IL', 'Toulouse, France', 'Bethesda, MD', 'Falls Church, VA', 'Waltham, MA',
        'Reston, VA', 'Charlotte, NC', 'London, UK', 'Paris, France', 'Melbourne, FL'
    ],
    'Primary_Product': [
        'Commercial Aircraft', 'Commercial Aircraft', 'Defense Systems', 'Defense Systems', 'Aerospace Systems',
        'Aerospace & Defense', 'Avionics Systems', 'Aircraft Engines', 'Aircraft Engines', 'Communication Systems'
    ],
    'Annual_Revenue_B': [
        77.8, 70.5, 67.0, 36.8, 65.4,
        39.4, 15.8, 16.9, 22.3, 18.2
    ],
    'Employee_Count': [
        156000, 134000, 116000, 95000, 182000,
        106000, 97000, 42000, 78000, 48000
    ],
    'Certification_Level': [
        'AS9100 Rev D', 'AS9100 Rev D', 'AS9100 Rev D', 'AS9100 Rev C', 'AS9100 Rev D',
        'AS9100 Rev D', 'AS9100 Rev D', 'AS9100 Rev C', 'AS9100 Rev D', 'AS9100 Rev D'
    ],
    'Contract_Expiry': [
        '2026-12-31', '2025-08-15', '2027-03-30', '2025-11-20', '2026-06-30',
        '2025-09-15', '2026-01-31', '2025-07-30', '2026-10-15', '2025-12-31'
    ]
}

# Create DataFrame
df = pd.DataFrame(data)

# Save to Excel
df.to_excel('aerospace_manufacturing.xlsx', index=False)

# Create column config with real companies as ID fields
config = {
    "general_notes": "This table tracks aerospace manufacturing suppliers and their key capabilities. Focus is on validating supplier information, certifications, contract details, and operational metrics for supply chain management and vendor assessment.",
    "default_model": "sonar-pro",
    "default_search_context_size": "low",
    "validation_targets": [
        {
            "column": "Company_Name",
            "description": "Official name of the aerospace company",
            "importance": "ID",
            "format": "String",
            "notes": "Full corporate name - these are real aerospace companies",
            "examples": ["Boeing Company", "Airbus SE", "Lockheed Martin"],
            "search_group": 0
        },
        {
            "column": "Headquarters",
            "description": "Location of company headquarters",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "City, State/Country format - will be validated through search",
            "examples": ["Chicago, IL", "Toulouse, France", "Bethesda, MD"],
            "search_group": 1,
            "search_context_size": "medium"
        },
        {
            "column": "Primary_Product",
            "description": "Main product category or service offering",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "Primary aerospace product line",
            "examples": ["Commercial Aircraft", "Defense Systems", "Aerospace Systems"],
            "search_group": 1
        },
        {
            "column": "Annual_Revenue_B",
            "description": "Annual revenue in billions USD",
            "importance": "CRITICAL",
            "format": "Number",
            "notes": "Total annual revenue in billions",
            "examples": ["77.8", "70.5", "67.0"],
            "search_group": 2,
            "search_context_size": "medium"
        },
        {
            "column": "Employee_Count",
            "description": "Total number of employees worldwide",
            "importance": "HIGH",
            "format": "Number",
            "notes": "Global workforce count",
            "examples": ["156000", "134000", "116000"],
            "search_group": 2
        },
        {
            "column": "Certification_Level",
            "description": "Aerospace quality management certification",
            "importance": "HIGH",
            "format": "String",
            "notes": "AS9100 or equivalent aerospace quality standard",
            "examples": ["AS9100 Rev D", "AS9100 Rev C"],
            "search_group": 3,
            "search_context_size": "high"
        },
        {
            "column": "Contract_Expiry",
            "description": "Date when current contract expires",
            "importance": "HIGH",
            "format": "Date",
            "notes": "Must be in YYYY-MM-DD format",
            "examples": ["2026-12-31", "2025-08-15", "2027-03-30"],
            "search_group": 3
        }
    ]
}

# Save config
with open('aerospace_manufacturing_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("Aerospace manufacturing test case created successfully!") 