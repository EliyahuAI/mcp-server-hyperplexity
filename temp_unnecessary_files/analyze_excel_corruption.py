#!/usr/bin/env python3
"""
Analyze the Excel file corruption issue by examining specific patterns.
"""

import zipfile
import xml.etree.ElementTree as ET
import re

def analyze_excel_file(excel_path):
    """Analyze Excel file for potential corruption causes."""
    print(f"\nAnalyzing: {excel_path}")
    print("="*60)
    
    with zipfile.ZipFile(excel_path, 'r') as zf:
        # Check sharedStrings.xml specifically
        if 'xl/sharedStrings.xml' in zf.namelist():
            content = zf.read('xl/sharedStrings.xml').decode('utf-8')
            
            # Check for various potential issues
            print("\nSharedStrings.xml Analysis:")
            print(f"- File size: {len(content)} bytes")
            
            # Count string items
            strings_count = content.count('<si>')
            print(f"- Number of shared strings: {strings_count}")
            
            # Look for very long strings
            pattern = r'<t[^>]*>([^<]+)</t>'
            matches = re.findall(pattern, content)
            if matches:
                max_len = max(len(m) for m in matches)
                print(f"- Longest string: {max_len} characters")
                
                # Find strings with special patterns
                newline_strings = [m for m in matches if '\n' in m or '&#10;' in m or '&#xA;' in m]
                print(f"- Strings with newlines: {len(newline_strings)}")
                
                # Check for problematic characters
                for i, s in enumerate(matches[:5]):  # Check first 5
                    if any(ord(c) < 32 and ord(c) not in (9, 10, 13) for c in s):
                        print(f"  WARNING: String {i} has control characters")
            
            # Check for specific XML issues
            try:
                root = ET.fromstring(content)
                print("- XML parsing: OK")
            except ET.ParseError as e:
                print(f"- XML PARSE ERROR: {e}")
        
        # Check worksheet files
        for sheet_name in ['xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml', 'xl/worksheets/sheet3.xml']:
            if sheet_name in zf.namelist():
                print(f"\n{sheet_name} Analysis:")
                content = zf.read(sheet_name).decode('utf-8')
                print(f"- File size: {len(content)} bytes")
                
                # Count cells
                cell_count = content.count('<c ')
                print(f"- Number of cells: {cell_count}")
                
                # Check for inline strings vs shared strings
                inline_count = content.count('<is>')
                shared_count = content.count('<v>')
                print(f"- Inline strings: {inline_count}, Shared string refs: {shared_count}")
                
                # Look for comments
                if 'xl/comments1.xml' in zf.namelist():
                    comments_content = zf.read('xl/comments1.xml').decode('utf-8')
                    comment_count = comments_content.count('<comment ')
                    print(f"- Comments: {comment_count}")

if __name__ == "__main__":
    # Analyze the attached file
    analyze_excel_file("validation_results_enhanced.xlsx") 