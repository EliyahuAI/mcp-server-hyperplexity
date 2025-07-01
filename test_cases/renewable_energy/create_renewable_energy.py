import pandas as pd
import json

# Renewable energy projects test data with real developers as ID fields
data = {
    'Developer': [
        'NextEra Energy', 'Orsted', 'First Solar', 'Vestas Wind Systems', 'Tesla Energy',
        'SunPower Corporation', 'General Electric', 'Enphase Energy', 'Equinor ASA', 'AES Corporation'
    ],
    'Project_Name': [
        'Sunrise Solar Farm', 'Pacific Wind Power', 'Desert Sun Array', 'Mountain Ridge Wind',
        'Coastal Battery Storage', 'Valley Solar Park', 'Highland Wind Farm', 'Urban Solar Grid',
        'Offshore Wind Alpha', 'Green Valley Storage'
    ],
    'Technology_Type': [
        'Solar PV', 'Onshore Wind', 'Solar PV', 'Onshore Wind', 'Battery Storage',
        'Solar PV', 'Onshore Wind', 'Solar PV', 'Offshore Wind', 'Battery Storage'
    ],
    'Capacity_MW': [
        250.5, 180.0, 320.8, 150.0, 100.0,
        420.2, 200.5, 85.3, 500.0, 150.0
    ],
    'Investment_M': [
        187.5, 234.0, 256.4, 178.5, 89.2,
        315.8, 198.7, 76.4, 1250.0, 134.5
    ],
    'Status': [
        'Under Construction', 'Operational', 'Permitted', 'Under Construction', 'Planning',
        'Operational', 'Under Construction', 'Operational', 'Planning', 'Permitted'
    ],
    'Expected_COD': [
        '2025-06-30', '2024-01-15', '2025-12-31', '2025-09-15', '2026-03-30',
        '2024-03-20', '2025-11-30', '2024-05-10', '2027-08-15', '2025-10-30'
    ]
}

# Create DataFrame
df = pd.DataFrame(data)

# Save to Excel
df.to_excel('renewable_energy.xlsx', index=False)

# Create column config with real developers as ID fields
config = {
    "general_notes": "This table tracks renewable energy projects in various stages of development. Focus is on validating project status, capacity, investment amounts, and developer information for energy sector analysis and investment tracking.",
    "default_model": "sonar-pro", 
    "default_search_context_size": "low",
    "validation_targets": [
        {
            "column": "Developer",
            "description": "Company developing the renewable energy project",
            "importance": "ID",
            "format": "String",
            "notes": "Primary developer or lead company - these are real energy companies",
            "examples": ["NextEra Energy", "Orsted", "First Solar"],
            "search_group": 0
        },
        {
            "column": "Project_Name",
            "description": "Official name of the renewable energy project",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "Public project name - will be validated through search",
            "examples": ["Sunrise Solar Farm", "Pacific Wind Power", "Desert Sun Array"],
            "search_group": 1,
            "search_context_size": "medium"
        },
        {
            "column": "Technology_Type",
            "description": "Type of renewable energy technology",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "Technology category (Solar PV, Wind, Storage, etc.)",
            "examples": ["Solar PV", "Onshore Wind", "Battery Storage"],
            "search_group": 1
        },
        {
            "column": "Capacity_MW",
            "description": "Generation capacity in megawatts",
            "importance": "CRITICAL",
            "format": "Number",
            "notes": "Installed or planned capacity in MW",
            "examples": ["250.5", "180.0", "320.8"],
            "search_group": 2
        },
        {
            "column": "Investment_M",
            "description": "Total project investment in millions USD",
            "importance": "HIGH",
            "format": "Number",
            "notes": "Total project cost in millions of dollars",
            "examples": ["187.5", "234.0", "256.4"],
            "search_group": 2
        },
        {
            "column": "Status",
            "description": "Current development status of the project",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "Development phase (Planning, Permitted, Under Construction, Operational)",
            "examples": ["Under Construction", "Operational", "Permitted"],
            "search_group": 3,
            "search_context_size": "medium"
        },
        {
            "column": "Expected_COD",
            "description": "Expected commercial operation date",
            "importance": "HIGH",
            "format": "Date",
            "notes": "Must be in YYYY-MM-DD format",
            "examples": ["2025-06-30", "2025-09-15", "2026-03-30"],
            "search_group": 3
        }
    ]
}

# Save config
with open('renewable_energy_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("Renewable energy test case created successfully!") 