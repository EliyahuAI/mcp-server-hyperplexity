#!/usr/bin/env python3
"""
Debug script to see what's happening with normal mode validation results
"""
import requests
import json

def debug_normal_mode():
    url = 'https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate'
    
    print("🔍 DEBUGGING NORMAL MODE VALIDATION")
    print("=" * 60)
    
    with open('test_cases/real_excel.xlsx', 'rb') as excel_file, \
         open('test_cases/simple_config.json', 'rb') as config_file:
        
        files = {
            'excel_file': ('test.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'config_file': ('config.json', config_file, 'application/json')
        }
        
        print("📤 Uploading files for normal mode processing...")
        response = requests.post(url, files=files, timeout=60)
        
        print(f"📡 Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n📊 RESPONSE DATA:")
            print(f"Status: {data.get('status')}")
            print(f"Message: {data.get('message')}")
            print(f"Total rows: {data.get('total_rows')}")
            print(f"Processing time: {data.get('processing_time')}")
            print(f"Session ID: {data.get('session_id')}")
            
            # Test download to see what's in the file
            download_url = data.get('download_url')
            if download_url:
                print(f"\n⬇️  TESTING DOWNLOAD...")
                download_response = requests.get(download_url, timeout=30)
                print(f"Download status: {download_response.status_code}")
                
                if download_response.status_code == 200:
                    print(f"File size: {len(download_response.content)} bytes")
                    
                    # Save the file temporarily to check contents
                    with open('debug_download.zip', 'wb') as f:
                        f.write(download_response.content)
                    
                    # Check ZIP contents
                    import zipfile
                    try:
                        with zipfile.ZipFile('debug_download.zip', 'r') as zip_file:
                            file_list = zip_file.namelist()
                            print(f"📁 ZIP contains: {', '.join(file_list)}")
                            
                            # Check if we have the enhanced Excel file
                            if 'validation_results_enhanced.xlsx' in file_list:
                                print("✅ Enhanced Excel file found!")
                                
                                # Check Excel file size
                                info = zip_file.getinfo('validation_results_enhanced.xlsx')
                                print(f"Excel file size: {info.file_size} bytes")
                            else:
                                print("❌ No enhanced Excel file found")
                                
                                # Check what's in README.txt to understand the issue
                                if 'README.txt' in file_list:
                                    readme_content = zip_file.read('README.txt').decode('utf-8')
                                    print(f"\n📖 README.txt content:")
                                    print(readme_content[:500] + "..." if len(readme_content) > 500 else readme_content)
                    except Exception as e:
                        print(f"❌ Error reading ZIP file: {e}")
                
                else:
                    print(f"❌ Download failed: {download_response.status_code}")
                    print(f"Error response: {download_response.text}")
            else:
                print("❌ No download URL in response")
        else:
            print(f"❌ API call failed: {response.status_code}")
            print(f"Error response: {response.text}")

def debug_preview_mode():
    """Compare with preview mode to see if validation works there"""
    url = 'https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate?preview_first_row=true'
    
    print("\n🔍 DEBUGGING PREVIEW MODE FOR COMPARISON")
    print("=" * 60)
    
    with open('test_cases/real_excel.xlsx', 'rb') as excel_file, \
         open('test_cases/simple_config.json', 'rb') as config_file:
        
        files = {
            'excel_file': ('test.xlsx', excel_file, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            'config_file': ('config.json', config_file, 'application/json')
        }
        
        print("📤 Uploading files for preview mode...")
        response = requests.post(url, files=files, timeout=60)
        
        print(f"📡 Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Total rows: {data.get('total_rows')}")
            print(f"Processing time: {data.get('first_row_processing_time')}")
            
            # Check if we got real validation results
            markdown = data.get('markdown_table', '')
            if 'FAP' in markdown or 'Solid tumors' in markdown:
                print("✅ Preview mode has real validation results")
            else:
                print("❌ Preview mode shows placeholder data")
                
            print(f"\n📊 Markdown preview:")
            print(markdown)
        else:
            print(f"❌ Preview failed: {response.status_code}")

if __name__ == "__main__":
    debug_normal_mode()
    debug_preview_mode() 