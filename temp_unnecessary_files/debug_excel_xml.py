#!/usr/bin/env python3
"""
Debug Excel XML corruption issues by examining the raw XML structure.
"""

import zipfile
import xml.etree.ElementTree as ET
import sys
import re

def check_excel_xml(excel_path):
    """Examine Excel file's internal XML structure for corruption."""
    print(f"\nAnalyzing Excel file: {excel_path}")
    print("="*60)
    
    try:
        with zipfile.ZipFile(excel_path, 'r') as zf:
            # List all files in the Excel archive
            print("\nFiles in Excel archive:")
            for info in zf.filelist:
                print(f"  {info.filename} ({info.file_size} bytes)")
            
            # Check key XML files
            xml_files_to_check = [
                'xl/workbook.xml',
                'xl/worksheets/sheet1.xml',
                'xl/worksheets/sheet2.xml', 
                'xl/worksheets/sheet3.xml',
                'xl/sharedStrings.xml',
                'xl/styles.xml',
                'xl/comments1.xml'
            ]
            
            for xml_file in xml_files_to_check:
                if xml_file in zf.namelist():
                    print(f"\n\nChecking {xml_file}:")
                    try:
                        content = zf.read(xml_file).decode('utf-8')
                        
                        # Check for common XML issues
                        print(f"  Size: {len(content)} bytes")
                        
                        # Look for unescaped special characters
                        unescaped = re.findall(r'[^>](&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;))', content)
                        if unescaped:
                            print(f"  WARNING: Found unescaped ampersands: {unescaped[:5]}")
                        
                        # Look for control characters
                        control_chars = []
                        for i, char in enumerate(content):
                            code = ord(char)
                            if code < 32 and code not in (9, 10, 13):
                                control_chars.append((i, code, repr(char)))
                        
                        if control_chars:
                            print(f"  WARNING: Found {len(control_chars)} control characters:")
                            for pos, code, char in control_chars[:5]:
                                print(f"    Position {pos}: ASCII {code} {char}")
                        
                        # Try to parse as XML
                        try:
                            root = ET.fromstring(content)
                            print(f"  XML parsing: OK")
                            
                            # Count elements
                            element_count = len(list(root.iter()))
                            print(f"  Total elements: {element_count}")
                            
                        except ET.ParseError as e:
                            print(f"  XML PARSE ERROR: {e}")
                            # Show context around error
                            if hasattr(e, 'position'):
                                line, col = e.position
                                lines = content.split('\n')
                                if line <= len(lines):
                                    print(f"  Error context (line {line}):")
                                    start = max(0, line - 2)
                                    end = min(len(lines), line + 2)
                                    for i in range(start, end):
                                        prefix = ">>> " if i == line - 1 else "    "
                                        print(f"  {prefix}{lines[i][:100]}...")
                        
                    except Exception as e:
                        print(f"  ERROR reading {xml_file}: {e}")
                else:
                    print(f"\n{xml_file}: Not found")
                    
    except Exception as e:
        print(f"\nERROR: Could not open Excel file: {e}")
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_excel_xml(sys.argv[1])
    else:
        print("Usage: python debug_excel_xml.py <excel_file>")
        print("\nLooking for any Excel files in current directory...")
        import glob
        excel_files = glob.glob("*.xlsx")
        for excel_file in excel_files[:5]:  # Check first 5 files
            check_excel_xml(excel_file) 