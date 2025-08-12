#!/usr/bin/env python3
"""
Config Generator - Step 1: Basic Table Analysis
Building incrementally from test_validation.py

This step focuses on:
1. Reading and analyzing Excel files like test_validation.py does
2. Using existing prompt loading infrastructure
3. Basic table structure analysis
"""

import argparse
import json
import pandas as pd
import yaml
from pathlib import Path
import os
import sys
from datetime import datetime

# Default file paths
DEFAULT_EXCEL = r"tables\RatioCompetitiveIntelligence\RatioCompetitiveIntelligence_Verified1.xlsx"
DEFAULT_CONFIG = r"tables\RatioCompetitiveIntelligence\column_config_simplified.json"
DEFAULT_PROMPTS = r"src\prompts.yml"
DEFAULT_CONFIG_PROMPT = r"prompts\generate_column_config_prompt.md"

class PromptLoader:
    """Load prompts from various sources"""
    
    def __init__(self, prompts_yml_path=DEFAULT_PROMPTS):
        self.prompts_yml_path = prompts_yml_path
        self.prompts = {}
        self.load_prompts()
    
    def load_prompts(self):
        """Load prompts from prompts.yml if it exists"""
        if os.path.exists(self.prompts_yml_path):
            try:
                with open(self.prompts_yml_path, 'r', encoding='utf-8') as f:
                    self.prompts = yaml.safe_load(f)
                print(f"Loaded prompts from {self.prompts_yml_path}")
            except Exception as e:
                print(f"Error loading prompts.yml: {e}")
                self.prompts = {}
    
    def load_config_generation_prompt(self, prompt_path=DEFAULT_CONFIG_PROMPT):
        """Load the config generation prompt from markdown file"""
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                print(f"Loaded config generation prompt from {prompt_path}")
                return content
            except Exception as e:
                print(f"Error loading config prompt: {e}")
                return None
        else:
            print(f"Config prompt file not found: {prompt_path}")
            return None
    
    def get_prompt(self, prompt_name):
        """Get a prompt by name"""
        return self.prompts.get(prompt_name)

class TableAnalyzer:
    """Analyze Excel/CSV table structure and content"""
    
    def __init__(self):
        self.analysis_results = {}
    
    def analyze_table(self, file_path, sheet_name=None):
        """Analyze table structure and content"""
        print(f"\nAnalyzing Analyzing table: {file_path}")
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Read the file
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
                print(f"Loaded Loaded CSV: {df.shape[0]} rows, {df.shape[1]} columns")
            elif file_path.endswith(('.xlsx', '.xls')):
                # First, get all sheet names
                excel_file = pd.ExcelFile(file_path)
                available_sheets = excel_file.sheet_names
                print(f"Available Available sheets: {available_sheets}")
                
                # Use specified sheet or first sheet
                target_sheet = sheet_name if sheet_name else available_sheets[0]
                df = pd.read_excel(file_path, sheet_name=target_sheet)
                print(f"Loaded Loaded Excel sheet '{target_sheet}': {df.shape[0]} rows, {df.shape[1]} columns")
            else:
                raise ValueError(f"Unsupported file format: {file_path}")
        
        except Exception as e:
            print(f"ERROR Error reading file: {e}")
            raise
        
        # Analyze structure
        analysis = self._analyze_structure(df, file_path)
        
        # Store results
        self.analysis_results = analysis
        
        return analysis
    
    def _analyze_structure(self, df, file_path):
        """Analyze dataframe structure in detail"""
        print(f"\nAnalyzing Analyzing structure...")
        
        # Basic info
        basic_info = {
            'filename': os.path.basename(file_path),
            'shape': df.shape,
            'total_rows': df.shape[0],
            'total_columns': df.shape[1],
            'column_names': df.columns.tolist()
        }
        
        # Column analysis
        print(f"   Analyzing {len(df.columns)} columns...")
        column_analysis = {}
        
        for col in df.columns:
            col_info = self._analyze_column(df[col], col)
            column_analysis[col] = col_info
            print(f"   OK {col}: {col_info['data_type']}, {col_info['unique_count']} unique, {col_info['null_count']} nulls")
        
        # Infer relationships and groupings
        groupings = self._infer_search_groups(df, column_analysis)
        
        # Infer domain/purpose
        domain_info = self._infer_domain_and_purpose(df, column_analysis)
        
        # Sample data (first 3 rows)
        sample_data = df.head(3).to_dict('records')
        
        analysis = {
            'basic_info': basic_info,
            'column_analysis': column_analysis,
            'inferred_groupings': groupings,
            'domain_info': domain_info,
            'sample_data': sample_data,
            'analysis_timestamp': datetime.now().isoformat()
        }
        
        return analysis
    
    def _analyze_column(self, series, column_name):
        """Analyze individual column"""
        # Basic stats
        total_count = len(series)
        null_count = series.isnull().sum()
        unique_count = series.nunique()
        
        # Data type inference
        data_type = self._infer_data_type(series)
        
        # Sample values (non-null)
        sample_values = series.dropna().head(5).tolist()
        
        # Importance inference
        importance = self._infer_importance(column_name, series)
        
        # Format inference
        format_info = self._infer_format(series, data_type)
        
        return {
            'data_type': data_type,
            'null_count': int(null_count),
            'unique_count': int(unique_count),
            'total_count': int(total_count),
            'null_percentage': round(null_count / total_count * 100, 2),
            'unique_percentage': round(unique_count / total_count * 100, 2),
            'sample_values': sample_values,
            'inferred_importance': importance,
            'inferred_format': format_info,
            'is_likely_id': unique_count == total_count and null_count == 0,
            'has_pattern': self._detect_pattern(series)
        }
    
    def _infer_data_type(self, series):
        """Infer semantic data type"""
        # Check for URLs
        if series.dtype == 'object':
            sample_str = str(series.dropna().iloc[0]) if len(series.dropna()) > 0 else ""
            if sample_str.startswith(('http://', 'https://')):
                return 'URL'
            if '@' in sample_str and '.' in sample_str:
                return 'Email'
            if any(keyword in sample_str.lower() for keyword in ['nct', 'clinical', 'trial']):
                return 'Clinical_Trial_ID'
        
        # Check for dates
        if 'date' in str(series.dtype).lower() or pd.api.types.is_datetime64_any_dtype(series):
            return 'Date'
        
        # Check for numbers
        if pd.api.types.is_numeric_dtype(series):
            return 'Number'
        
        # Default to string
        return 'String'
    
    def _infer_importance(self, column_name, series):
        """Infer importance level from column name and data characteristics"""
        col_lower = column_name.lower()
        
        # ID patterns
        if any(keyword in col_lower for keyword in ['id', 'code', 'name', 'key']):
            if series.nunique() == len(series):  # Unique values
                return 'ID'
        
        # Critical patterns
        if any(keyword in col_lower for keyword in ['status', 'stage', 'phase', 'indication', 'target']):
            return 'CRITICAL'
        
        # High importance patterns
        if any(keyword in col_lower for keyword in ['trial', 'development', 'regulatory', 'fda', 'launch']):
            return 'HIGH'
        
        # Medium importance patterns
        if any(keyword in col_lower for keyword in ['partner', 'company', 'designation']):
            return 'MEDIUM'
        
        # Low importance patterns
        if any(keyword in col_lower for keyword in ['note', 'comment', 'news', 'recent']):
            return 'LOW'
        
        return 'MEDIUM'  # Default
    
    def _infer_format(self, series, data_type):
        """Infer format specifications"""
        if data_type == 'Date':
            return 'Date (YYYY-MM-DD or similar)'
        elif data_type == 'Number':
            return 'Number'
        elif data_type == 'URL':
            return 'URL'
        elif data_type == 'Email':
            return 'Email'
        elif data_type == 'Clinical_Trial_ID':
            return 'Clinical Trial ID (NCT format)'
        else:
            return 'String'
    
    def _detect_pattern(self, series):
        """Detect if there's a consistent pattern in the data"""
        if series.dtype != 'object':
            return None
        
        # Check for common patterns
        non_null = series.dropna()
        if len(non_null) == 0:
            return None
        
        # Check for NCT pattern
        if non_null.str.contains('NCT', case=False, na=False).any():
            return 'NCT_ID'
        
        # Check for phase pattern
        if non_null.str.contains('Phase', case=False, na=False).any():
            return 'CLINICAL_PHASE'
        
        # Check for year pattern
        if non_null.str.contains(r'20\d{2}', na=False).any():
            return 'YEAR'
        
        return None
    
    def _infer_search_groups(self, df, column_analysis):
        """Infer logical search groups based on column relationships"""
        groups = []
        
        # Group 0: ID fields
        id_columns = [col for col, info in column_analysis.items() 
                     if info['inferred_importance'] == 'ID']
        if id_columns:
            groups.append({
                'group_id': 0,
                'group_name': 'Identification',
                'description': 'Product and company identification fields',
                'columns': id_columns,
                'reasoning': 'ID fields typically used for context'
            })
        
        # Group 1: Product characteristics
        product_columns = [col for col in df.columns 
                          if any(keyword in col.lower() for keyword in 
                                ['target', 'indication', 'modality', 'radionuclide'])]
        if product_columns:
            groups.append({
                'group_id': 1,
                'group_name': 'Product Characteristics',
                'description': 'Core product features and scientific details',
                'columns': product_columns,
                'reasoning': 'Product details often found together in scientific sources'
            })
        
        # Group 2: Development status
        dev_columns = [col for col in df.columns 
                      if any(keyword in col.lower() for keyword in 
                            ['stage', 'phase', 'trial', 'development'])]
        if dev_columns:
            groups.append({
                'group_id': 2,
                'group_name': 'Development Status',
                'description': 'Clinical development and trial information',
                'columns': dev_columns,
                'reasoning': 'Development status info typically appears together'
            })
        
        # Group 3: Commercial/regulatory
        commercial_columns = [col for col in df.columns 
                            if any(keyword in col.lower() for keyword in 
                                  ['fda', 'regulatory', 'launch', 'partner', 'designation'])]
        if commercial_columns:
            groups.append({
                'group_id': 3,
                'group_name': 'Commercial Information',
                'description': 'Regulatory and commercial development details',
                'columns': commercial_columns,
                'reasoning': 'Commercial info often found in business/regulatory sources'
            })
        
        # Group 4: News/updates
        news_columns = [col for col in df.columns 
                       if any(keyword in col.lower() for keyword in 
                             ['news', 'recent', 'update', 'development'])]
        if news_columns:
            groups.append({
                'group_id': 4,
                'group_name': 'Recent Developments',
                'description': 'Latest news and updates',
                'columns': news_columns,
                'reasoning': 'News typically requires high-context search'
            })
        
        return groups
    
    def _infer_domain_and_purpose(self, df, column_analysis):
        """Infer the domain and purpose of the table"""
        columns_text = ' '.join(df.columns).lower()
        
        # Pharmaceutical/biotech indicators
        pharma_keywords = ['drug', 'pharma', 'clinical', 'trial', 'fda', 'target', 'indication', 
                          'therapeutic', 'radionuclide', 'modality', 'development', 'phase']
        pharma_score = sum(1 for keyword in pharma_keywords if keyword in columns_text)
        
        # Financial indicators
        financial_keywords = ['revenue', 'profit', 'investment', 'market', 'valuation', 'price']
        financial_score = sum(1 for keyword in financial_keywords if keyword in columns_text)
        
        # Research indicators
        research_keywords = ['research', 'study', 'academic', 'publication', 'journal']
        research_score = sum(1 for keyword in research_keywords if keyword in columns_text)
        
        # Determine domain
        if pharma_score > max(financial_score, research_score):
            domain = 'pharmaceutical'
            purpose = 'pharmaceutical competitive intelligence and pipeline tracking'
        elif financial_score > research_score:
            domain = 'financial'
            purpose = 'financial analysis and investment tracking'
        elif research_score > 0:
            domain = 'research'
            purpose = 'research data collection and analysis'
        else:
            domain = 'general'
            purpose = 'general data tracking and analysis'
        
        return {
            'inferred_domain': domain,
            'inferred_purpose': purpose,
            'domain_confidence': max(pharma_score, financial_score, research_score),
            'keyword_scores': {
                'pharmaceutical': pharma_score,
                'financial': financial_score,
                'research': research_score
            }
        }
    
    def print_analysis_summary(self):
        """Print a formatted summary of the analysis"""
        if not self.analysis_results:
            print("ERROR No analysis results available")
            return
        
        analysis = self.analysis_results
        
        print("\n" + "="*60)
        print("Loaded TABLE ANALYSIS SUMMARY")
        print("="*60)
        
        # Basic info
        basic = analysis['basic_info']
        print(f"File: {basic['filename']}")
        print(f"Size: {basic['total_rows']} rows × {basic['total_columns']} columns")
        
        # Domain info
        domain = analysis['domain_info']
        print(f"Domain: {domain['inferred_domain']} (confidence: {domain['domain_confidence']})")
        print(f"Purpose: {domain['inferred_purpose']}")
        
        # Column summary
        print(f"\nAvailable COLUMN SUMMARY:")
        for col, info in analysis['column_analysis'].items():
            print(f"  {col}:")
            print(f"    Type: {info['data_type']}, Importance: {info['inferred_importance']}")
            print(f"    Data: {info['unique_count']} unique/{info['total_count']} total, {info['null_count']} nulls")
            # Handle Unicode characters in sample values
            sample_values = info['sample_values'][:3]
            # Clean Unicode characters
            clean_samples = []
            for val in sample_values:
                clean_val = str(val).encode('ascii', 'ignore').decode('ascii')
                clean_samples.append(clean_val)
            print(f"    Sample: {clean_samples}")
        
        # Groupings
        print(f"\nINFERRED SEARCH GROUPS:")
        for group in analysis['inferred_groupings']:
            print(f"  Group {group['group_id']}: {group['group_name']}")
            print(f"    Columns: {', '.join(group['columns'])}")
            print(f"    Reasoning: {group['reasoning']}")
        
        print("\n" + "="*60)

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Config Generator Step 1: Basic Table Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--excel', 
                       default=DEFAULT_EXCEL,
                       help='Path to Excel file')
    
    parser.add_argument('--sheet', 
                       help='Sheet name (optional)')
    
    parser.add_argument('--output', 
                       help='Output file for analysis results (JSON)')
    
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Verbose output')
    
    return parser.parse_args()

def main():
    """Main function"""
    args = parse_arguments()
    
    print("CONFIG GENERATOR - STEP 1: TABLE ANALYSIS")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Initialize components
        prompt_loader = PromptLoader()
        analyzer = TableAnalyzer()
        
        # Test prompt loading
        print("\nTesting Testing prompt loading...")
        config_prompt = prompt_loader.load_config_generation_prompt()
        if config_prompt:
            print(f"   Config prompt loaded: {len(config_prompt)} characters")
        
        # Test existing prompts
        multiplex_prompt = prompt_loader.get_prompt('multiplex_validation')
        if multiplex_prompt:
            print(f"   Multiplex prompt loaded: {len(multiplex_prompt)} characters")
        
        # Analyze table
        print("\nLoaded Analyzing table...")
        analysis = analyzer.analyze_table(args.excel, args.sheet)
        
        # Print summary
        analyzer.print_analysis_summary()
        
        # Save results if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, default=str)
            
            print(f"\nSaved Analysis saved to: {output_path}")
        
        print("\nSUCCESS Step 1 completed successfully!")
        
    except Exception as e:
        print(f"\nERROR Error: {str(e)}")
        import traceback
        if args.verbose:
            traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())