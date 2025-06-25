#!/usr/bin/env python3
"""
Script to show exact outputs from both preview and normal modes
"""
import requests
import json

API_URL = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate"

def test_preview_mode():
    """Test preview mode and show markdown output"""
    print("🔍 PREVIEW MODE OUTPUT:")
    print("=" * 60)
    
    with open('test_cases/real_excel.xlsx', 'rb') as excel_file, \
         open('test_cases/real_config.json', 'rb') as config_file:
        
        files = {
            'excel_file': ('real_excel.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'config_file': ('real_config.json', config_file, 'application/json')
        }
        
        response = requests.post(f"{API_URL}?preview_first_row=true", files=files)
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Session ID: {data.get('session_id')}")
            print(f"Processing time: {data.get('first_row_processing_time', 0):.2f}s")
            print(f"Total rows: {data.get('total_rows')}")
            print()
            print("📋 MARKDOWN TABLE:")
            print(data.get('markdown_table', 'No markdown table'))
            print()
            if 'note' in data:
                print(f"⚠️  Note: {data['note']}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)

def test_normal_mode():
    """Test normal mode and show download link"""
    print("\n🔗 NORMAL MODE OUTPUT:")
    print("=" * 60)
    
    with open('test_cases/real_excel.xlsx', 'rb') as excel_file, \
         open('test_cases/real_config.json', 'rb') as config_file:
        
        files = {
            'excel_file': ('real_excel.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'config_file': ('real_config.json', config_file, 'application/json')
        }
        
        response = requests.post(f"{API_URL}?preview_first_row=false", files=files)
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Session ID: {data.get('session_id')}")
            print(f"Password: {data.get('password')}")
            print(f"Message: {data.get('message')}")
            print(f"Estimated completion: {data.get('estimated_completion')}")
            print()
            print("📥 DOWNLOAD LINK:")
            download_url = data.get('download_url', '')
            print(download_url)
            print()
            
            # Test if link works
            if download_url:
                try:
                    download_response = requests.head(download_url)
                    print(f"🔄 Link Status: {download_response.status_code}")
                    if download_response.status_code == 200:
                        print(f"✅ Link accessible - Content Length: {download_response.headers.get('Content-Length', 'Unknown')} bytes")
                    else:
                        print(f"❌ Link not accessible")
                except Exception as e:
                    print(f"❌ Error testing link: {e}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)

if __name__ == "__main__":
    test_preview_mode()
    test_normal_mode() 