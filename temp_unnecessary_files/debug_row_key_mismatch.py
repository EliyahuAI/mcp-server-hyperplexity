#!/usr/bin/env python3
"""
Debug script to check row key mismatches due to special characters.
"""

import sys
import json
import pandas as pd
sys.path.append('src')

def debug_row_key_mismatch():
    """Debug row key mismatches in the Excel processing pipeline."""
    
    print("🔍 DEBUGGING ROW KEY MISMATCH WITH SPECIAL CHARACTERS")
    print("="*60)
    
    # The Excel file you're using
    excel_path = r"tables/RatioCompetitiveIntelligence/RatioCompetitiveIntelligence_validatedAE_1_20250529_105147.xlsx"
    
    # Load Excel data
    print("\n📊 Loading Excel data...")
    df = pd.read_excel(excel_path, sheet_name=0)
    first_row = df.iloc[0]
    
    # Show the raw values
    print("\n📝 RAW VALUES FROM EXCEL:")
    for col in ['Product Name', 'Developer', 'Target']:
        value = first_row[col]
        print(f"\n{col}: '{value}'")
        print(f"   Hex: {value.encode('utf-8').hex()}")
        
        # Check for special characters
        if '\u2011' in str(value):
            print("   ⚠️  Contains non-breaking hyphen (U+2011)")
        if '\u202f' in str(value):
            print("   ⚠️  Contains narrow no-break space (U+202F)")
        if '\xa0' in str(value):
            print("   ⚠️  Contains non-breaking space (U+00A0)")
    
    # Generate row key with different methods
    from row_key_utils import generate_row_key
    
    # Convert to row data
    row_data = {}
    for col, val in first_row.to_dict().items():
        if not (isinstance(val, float) and pd.isna(val)):
            if not pd.isna(val) and val is not None:
                row_data[col] = str(val)
            else:
                row_data[col] = None
    
    primary_keys = ['Product Name', 'Developer', 'Target']
    
    # Generate normalized row key
    normalized_key = generate_row_key(row_data, primary_keys)
    print(f"\n🔑 NORMALIZED ROW KEY: '{normalized_key}'")
    
    # Create raw key without normalization
    raw_key_parts = []
    for pk in primary_keys:
        if pk in row_data and row_data[pk]:
            raw_key_parts.append(str(row_data[pk]))
    raw_key = "||".join(raw_key_parts)
    print(f"\n🔑 RAW ROW KEY: '{raw_key}'")
    
    # Compare
    if raw_key != normalized_key:
        print("\n❌ ROW KEYS DO NOT MATCH!")
        print(f"   Raw length: {len(raw_key)}")
        print(f"   Normalized length: {len(normalized_key)}")
        
        # Find differences
        print("\n   Character-by-character comparison:")
        for i, (r, n) in enumerate(zip(raw_key, normalized_key)):
            if r != n:
                print(f"   Position {i}: '{r}' (U+{ord(r):04X}) → '{n}' (U+{ord(n):04X})")
    else:
        print("\n✅ Row keys match")
    
    # Load validation history to see what key it uses
    from lambda_test_json_clean import load_validation_history_from_excel
    validation_history = load_validation_history_from_excel(excel_path)
    
    print(f"\n📚 VALIDATION HISTORY KEYS:")
    for key in validation_history.keys():
        print(f"   '{key}'")
        if key == normalized_key:
            print("   ✅ Matches normalized key")
        elif key == raw_key:
            print("   ✅ Matches raw key")
        else:
            print("   ❌ Doesn't match either key")
    
    # Check what batch_validate would do
    print("\n🔧 BATCH_VALIDATE SIMULATION:")
    
    # This is what batch_validate does when creating payload
    batch_row_key = generate_row_key(row_data, primary_keys)
    print(f"   Batch validate would use: '{batch_row_key}'")
    
    # Check if this key exists in validation history
    if batch_row_key in validation_history:
        print("   ✅ This key EXISTS in validation history")
        print(f"   History fields: {list(validation_history[batch_row_key].keys())[:3]}...")
    else:
        print("   ❌ This key NOT FOUND in validation history")
    
    # Save debug info
    debug_info = {
        "raw_values": {
            "Product Name": first_row['Product Name'],
            "Developer": first_row['Developer'],
            "Target": first_row['Target']
        },
        "raw_key": raw_key,
        "normalized_key": normalized_key,
        "batch_validate_key": batch_row_key,
        "validation_history_keys": list(validation_history.keys()),
        "key_match": batch_row_key in validation_history
    }
    
    with open("debug_row_key_mismatch.json", 'w', encoding='utf-8') as f:
        json.dump(debug_info, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved debug info to: debug_row_key_mismatch.json")

if __name__ == "__main__":
    debug_row_key_mismatch() 