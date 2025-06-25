#!/usr/bin/env python3
"""
Debug Excel content to find what's causing corruption.
"""

import zipfile
import xml.etree.ElementTree as ET
import re
import sys

def analyze_excel_content(excel_path):
    """Analyze Excel content for potential issues."""
    print(f"\nAnalyzing content in: {excel_path}")
    print("="*60)
    
    with zipfile.ZipFile(excel_path, 'r') as zf:
        # Check shared strings for problematic content
        if 'xl/sharedStrings.xml' in zf.namelist():
            content = zf.read('xl/sharedStrings.xml').decode('utf-8')
            
            print("\nChecking for potential issues in shared strings:")
            
            # Look for specific patterns
            patterns_to_check = [
                (r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', 'Control characters (except tab/newline)'),
                (r'&(?!amp;|lt;|gt;|quot;|apos;)', 'Unescaped ampersands'),
                (r'<(?!/?[a-zA-Z])', 'Unescaped less-than'),
                (r'>(?![a-zA-Z])', 'Unescaped greater-than'),
                (r'[\x7F-\x9F]', 'High control characters'),
                (r'[\uD800-\uDFFF]', 'Unpaired surrogates'),
                (r'[\uFFFE\uFFFF]', 'Invalid Unicode characters'),
                (r'&amp;amp;', 'Double-escaped ampersands'),
                (r'&amp;lt;', 'Double-escaped less-than'),
                (r'&amp;gt;', 'Double-escaped greater-than'),
                (r'&amp;quot;', 'Double-escaped quotes'),
                (r'&amp;apos;', 'Double-escaped apostrophes'),
            ]
            
            issues_found = False
            for pattern, description in patterns_to_check:
                matches = re.findall(pattern, content)
                if matches:
                    print(f"\n✗ Found {description}: {len(matches)} occurrences")
                    # Show first few examples
                    for i, match in enumerate(matches[:5]):
                        # Find context around the match
                        idx = content.find(match)
                        start = max(0, idx - 20)
                        end = min(len(content), idx + len(match) + 20)
                        context = content[start:end]
                        print(f"  Example {i+1}: ...{repr(context)}...")
                    if len(matches) > 5:
                        print(f"  ... and {len(matches) - 5} more")
                    issues_found = True
            
            if not issues_found:
                print("✓ No obvious content issues found in shared strings")
            
            # Check for very long strings
            try:
                root = ET.fromstring(content)
                for i, si in enumerate(root.findall('.//si')):
                    text = ''.join(si.itertext())
                    if len(text) > 1000:
                        print(f"\nLong string at index {i}: {len(text)} characters")
                        print(f"  Preview: {text[:100]}...")
            except ET.ParseError as e:
                print(f"\n✗ XML Parse Error in shared strings: {e}")
        
        # Check worksheet content
        for sheet_name in ['xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml']:
            if sheet_name in zf.namelist():
                print(f"\n\nChecking {sheet_name}:")
                content = zf.read(sheet_name).decode('utf-8')
                
                # Look for inline strings (which might have unescaped content)
                inline_strings = re.findall(r'<is>(.*?)</is>', content, re.DOTALL)
                if inline_strings:
                    print(f"Found {len(inline_strings)} inline strings")
                    for i, inline in enumerate(inline_strings[:3]):
                        print(f"  Inline string {i+1}: {repr(inline[:100])}")
                
                # Check for formula errors
                formula_errors = re.findall(r'<f[^>]*>.*?#[A-Z]+!.*?</f>', content)
                if formula_errors:
                    print(f"Found {len(formula_errors)} formula errors")
                    for err in formula_errors[:3]:
                        print(f"  Formula error: {err}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        analyze_excel_content(sys.argv[1])
    else:
        # Default to the uploaded file
        analyze_excel_content("validation_results_enhanced.xlsx") 