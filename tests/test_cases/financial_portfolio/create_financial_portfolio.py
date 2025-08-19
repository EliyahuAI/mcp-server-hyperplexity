import pandas as pd
import json

# Financial portfolio test data with real companies as ID fields
data = {
    'Ticker_Symbol': [
        'AAPL', 'MSFT', 'AMZN', 'TSLA', 'META',
        'GOOGL', 'WMT', 'KO', 'GOOG', 'BRK.B'
    ],
    'Company_Name': [
        'Apple Inc.', 'Microsoft Corporation', 'Amazon.com Inc.', 'Tesla Inc.', 'Meta Platforms Inc.',
        'Alphabet Inc. Class A', 'Walmart Inc.', 'The Coca-Cola Company', 'Alphabet Inc. Class C', 'Berkshire Hathaway Inc.'
    ],
    'Asset_ID': [
        'US0378331005', 'US5949181045', 'US0231351067', 'US17275R1023', 'US30303M1027',
        'US88160R1014', 'US9311421039', 'US1912161007', 'US02079K3059', 'US0846707026'
    ],
    'Sector': [
        'Technology', 'Technology', 'Consumer Discretionary', 'Consumer Discretionary', 'Communication Services',
        'Communication Services', 'Consumer Staples', 'Consumer Staples', 'Communication Services', 'Financial Services'
    ],
    'Current_Price': [
        187.34, 412.78, 153.92, 248.66, 531.24,
        167.89, 72.18, 59.43, 166.12, 462.75
    ],
    'Market_Cap_B': [
        2876.5, 3067.2, 1598.4, 789.2, 1342.8,
        2089.4, 573.2, 253.7, 2067.8, 841.6
    ],
    'PE_Ratio': [
        29.2, 34.1, 52.8, 65.3, 24.7,
        26.8, 26.9, 23.1, 26.4, 11.2
    ],
    'Last_Updated': [
        '2024-12-15', '2024-12-15', '2024-12-15', '2024-12-15', '2024-12-15',
        '2024-12-15', '2024-12-15', '2024-12-15', '2024-12-15', '2024-12-15'
    ]
}

# Create DataFrame
df = pd.DataFrame(data)

# Save to Excel
df.to_excel('financial_portfolio.xlsx', index=False)

# Create column config with real companies as ID fields
config = {
    "general_notes": "This table tracks equity holdings in a diversified investment portfolio. Focus is on validating current market data, financial metrics, and company information for portfolio management and risk assessment.",
    "default_model": "sonar-pro",
    "default_search_context_size": "low",
    "validation_targets": [
        {
            "column": "Ticker_Symbol",
            "description": "Stock ticker symbol",
            "importance": "ID",
            "format": "String",
            "notes": "Exchange ticker symbol - real public company tickers",
            "examples": ["AAPL", "MSFT", "AMZN"],
            "search_group": 0
        },
        {
            "column": "Company_Name",
            "description": "Official registered name of the company",
            "importance": "ID",
            "format": "String",
            "notes": "Full legal entity name - real public companies",
            "examples": ["Apple Inc.", "Microsoft Corporation", "Amazon.com Inc."],
            "search_group": 0
        },
        {
            "column": "Asset_ID",
            "description": "CUSIP identifier for the security",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "9-character CUSIP code - will be validated through search",
            "examples": ["US0378331005", "US5949181045", "US0231351067"],
            "search_group": 1,
            "search_context_size": "medium"
        },
        {
            "column": "Sector",
            "description": "Industry sector classification",
            "importance": "CRITICAL",
            "format": "String",
            "notes": "GICS sector classification",
            "examples": ["Technology", "Consumer Discretionary", "Communication Services"],
            "search_group": 1
        },
        {
            "column": "Current_Price",
            "description": "Most recent stock price in USD",
            "importance": "CRITICAL",
            "format": "Number",
            "notes": "Price per share in US dollars",
            "examples": ["187.34", "412.78", "153.92"],
            "search_group": 2,
            "search_context_size": "medium"
        },
        {
            "column": "Market_Cap_B",
            "description": "Market capitalization in billions USD",
            "importance": "HIGH",
            "format": "Number",
            "notes": "Market cap in billions of dollars",
            "examples": ["2876.5", "3067.2", "1598.4"],
            "search_group": 2
        },
        {
            "column": "PE_Ratio",
            "description": "Price-to-earnings ratio",
            "importance": "HIGH",
            "format": "Number",
            "notes": "Current P/E ratio",
            "examples": ["29.2", "34.1", "52.8"],
            "search_group": 3
        },
        {
            "column": "Last_Updated",
            "description": "Date when the data was last updated",
            "importance": "MEDIUM",
            "format": "Date",
            "notes": "Must be in YYYY-MM-DD format",
            "examples": ["2024-12-15", "2024-12-14", "2024-12-13"],
            "search_group": 3
        }
    ]
}

# Save config
with open('financial_portfolio_config.json', 'w') as f:
    json.dump(config, f, indent=2)

print("Financial portfolio test case created successfully!") 