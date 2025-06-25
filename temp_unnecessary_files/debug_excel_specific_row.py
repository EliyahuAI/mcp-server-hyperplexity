#!/usr/bin/env python3
"""
Test creating Excel with specific data to isolate corruption issue.
"""

import xlsxwriter
import io

def test_excel_creation():
    """Test creating Excel with minimal data."""
    
    # Headers from the user
    headers = [
        'Index', 'Conference', 'Next Conference Name', 'Indication', 'Website',
        'Sponsoring Society', 'Frequency', 'Start Date', 'End Date', 'Location',
        'Abstract Submission Deadline', 'Notification Date', 'Late Breaker Option',
        'Late Breaker Deadline', 'Encores Allowed', 'Publication', 'Impact Factor',
        'Number of Attendees', 'Submitter/Presenter', 'Poster Upload Date', 
        'Poster Guidelines'
    ]
    
    # Test with different options
    test_cases = [
        {
            'name': 'minimal_no_options.xlsx',
            'options': {}
        },
        {
            'name': 'with_strings_to_urls_false.xlsx', 
            'options': {'strings_to_urls': False}
        },
        {
            'name': 'with_all_options.xlsx',
            'options': {'strings_to_urls': False, 'nan_inf_to_errors': True}
        },
        {
            'name': 'with_constant_memory.xlsx',
            'options': {'constant_memory': True, 'strings_to_urls': False}
        }
    ]
    
    for test in test_cases:
        print(f"\nCreating {test['name']} with options: {test['options']}")
        
        try:
            # Create workbook with specific options
            workbook = xlsxwriter.Workbook(test['name'], test['options'])
            worksheet = workbook.add_worksheet('Results')
            
            # Add headers
            for col, header in enumerate(headers):
                worksheet.write(0, col, header)
            
            # Add a simple test row
            test_row = [
                '6', 'Test Conference', 'TestConf 2025', 'Cardiology', 'https://test.com',
                'Test Society', 'annual', '2025-01-01', '2025-01-03', 'New York, NY',
                '2024-10-01', '2024-11-01', 'Yes', '2024-11-15', 'No',
                'Test Journal', '5.0', '1000', 'First Author', '2024-12-01',
                'Standard poster guidelines with some text'
            ]
            
            for col, value in enumerate(test_row):
                worksheet.write(1, col, value)
            
            workbook.close()
            print(f"  ✓ Created successfully")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")

if __name__ == "__main__":
    test_excel_creation()
    print("\nTest files created. Check if any of them open without corruption.") 