#!/usr/bin/env python3
import zipfile
import json

# Open the results ZIP
with zipfile.ZipFile('full_validation_results.zip', 'r') as zip_file:
    # Read validation results JSON
    with zip_file.open('validation_results.json') as json_file:
        results = json.load(json_file)
        
        print("Session ID:", results['session_id'])
        print("Total rows:", results['summary']['total_rows'])
        print("\nFields validated:", ', '.join(results['summary']['fields_validated']))
        print("\nConfidence distribution:")
        for level, count in results['summary']['confidence_distribution'].items():
            print(f"  {level}: {count}")
        
        print("\nSample validation result (first row):")
        if results['validation_results']:
            first_key = list(results['validation_results'].keys())[0]
            print(f"Row key: {first_key}")
            
            row_data = results['validation_results'][first_key]
            for field, data in row_data.items():
                if isinstance(data, dict) and 'value' in data:
                    print(f"  {field}: {data['value']} [{data.get('confidence_level', 'N/A')}]")
                    
    # Check the Excel file headers
    with zip_file.open('validation_results_enhanced.xlsx') as excel_file:
        import openpyxl
        import io
        
        wb = openpyxl.load_workbook(io.BytesIO(excel_file.read()))
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        print(f"\nExcel headers ({len(headers)}): {', '.join(str(h) for h in headers if h)}") 