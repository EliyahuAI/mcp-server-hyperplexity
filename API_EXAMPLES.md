# API Examples - Perplexity Validator

## Base URL
```
https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod
```

## Example 1: Synchronous Preview

Preview the first row for immediate validation testing.

### cURL
```bash
curl -X POST \
  "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate?preview_first_row=true" \
  -F "excel_file=@data.xlsx" \
  -F "config=@config.json" \
  -F "email=user@example.com"
```

### Python
```python
import requests

url = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate"
params = {"preview_first_row": "true"}

with open('data.xlsx', 'rb') as excel, open('config.json', 'rb') as config:
    files = {
        'excel_file': ('data.xlsx', excel, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        'config': ('config.json', config, 'application/json')
    }
    data = {'email': 'user@example.com'}
    
    response = requests.post(url, params=params, files=files, data=data)
    print(response.json())
```

### Response
```json
{
  "statusCode": 200,
  "session_id": "20250701123456_abc123",
  "preview_results": {
    "results": {
      "Product Name": ["Aspirin", 0.95, "Validated as correct pharmaceutical name"],
      "Development Stage": ["Phase 3", 0.89, "Confirmed clinical trial phase"]
    },
    "summary": {
      "total_cost": 0.057,
      "total_tokens": 7299,
      "processing_time": 0.437,
      "cache_hit_rate": 0.5
    }
  }
}
```

## Example 2: Asynchronous Preview

Preview multiple rows with background processing.

### cURL
```bash
curl -X POST \
  "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate?preview_first_row=true&async=true&max_rows=10" \
  -F "excel_file=@congress_list.xlsx" \
  -F "config=@congress_config.json" \
  -F "email=admin@company.com"
```

### Python
```python
import requests
import time

# Start async preview
url = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate"
params = {
    "preview_first_row": "true",
    "async": "true",
    "max_rows": "10"
}

with open('congress_list.xlsx', 'rb') as excel, open('congress_config.json', 'rb') as config:
    files = {
        'excel_file': ('congress_list.xlsx', excel),
        'config': ('congress_config.json', config)
    }
    data = {'email': 'admin@company.com'}
    
    response = requests.post(url, params=params, files=files, data=data)
    result = response.json()
    session_id = result['session_id']
    
# Poll for results
status_url = f"https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/status/{session_id}"
params = {"preview": "true"}

while True:
    status_response = requests.get(status_url, params=params)
    status = status_response.json()
    
    if status['status'] in ['completed', 'failed']:
        print(status)
        break
    
    print(f"Status: {status['status']}")
    time.sleep(5)
```

## Example 3: Full Validation

Process entire dataset with email delivery.

### cURL
```bash
curl -X POST \
  "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate?async=true&max_rows=100&batch_size=10" \
  -F "excel_file=@product_data.xlsx" \
  -F "config=@product_config.json" \
  -F "email=results@company.com"
```

### Python with Progress Tracking
```python
import requests
import time
import json

def validate_with_progress(excel_path, config_path, email, max_rows=None):
    # Start validation
    url = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate"
    params = {"async": "true"}
    if max_rows:
        params["max_rows"] = str(max_rows)
    
    with open(excel_path, 'rb') as excel, open(config_path, 'rb') as config:
        files = {
            'excel_file': (excel_path, excel),
            'config': (config_path, config)
        }
        data = {'email': email}
        
        response = requests.post(url, params=params, files=files, data=data)
        if response.status_code != 202:
            print(f"Error: {response.json()}")
            return
        
        result = response.json()
        session_id = result['session_id']
        print(f"Validation started: {session_id}")
    
    # Monitor progress
    status_url = f"https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/status/{session_id}"
    
    while True:
        status_response = requests.get(status_url)
        status = status_response.json()
        
        print(f"\nStatus: {status['status']}")
        
        if 'progress' in status:
            print(f"Progress: {json.dumps(status['progress'], indent=2)}")
        
        if status['status'] == 'completed':
            print(f"\n✅ Validation completed!")
            print(f"Results: {status.get('result_s3_key', 'N/A')}")
            print(f"Email sent: {status.get('email_sent', False)}")
            print(f"Metrics: {json.dumps(status.get('metrics', {}), indent=2)}")
            break
        elif status['status'] == 'failed':
            print(f"\n❌ Validation failed!")
            print(f"Error: {status.get('error', 'Unknown error')}")
            break
        
        time.sleep(10)

# Use it
validate_with_progress('data.xlsx', 'config.json', 'user@example.com', max_rows=50)
```

## Example 4: Config Validation

Validate configuration file before processing.

### cURL
```bash
curl -X POST \
  "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate-config" \
  -H "Content-Type: application/json" \
  -d @config.json
```

### Python
```python
import requests
import json

url = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate-config"

with open('config.json', 'r') as f:
    config = json.load(f)

response = requests.post(url, json=config)
result = response.json()

if result.get('valid'):
    print(f"✅ Config is valid! {result['validation_targets']} targets found.")
else:
    print(f"❌ Config is invalid: {result.get('message', 'Unknown error')}")
```

## Example 5: Batch Processing Script

Complete script for processing multiple files.

```python
import os
import glob
import requests
import json
import time
from datetime import datetime

class PerplexityValidator:
    def __init__(self, base_url, email):
        self.base_url = base_url
        self.email = email
        self.sessions = []
    
    def validate_file(self, excel_path, config_path, name=None):
        """Start validation for a single file"""
        url = f"{self.base_url}/validate"
        params = {"async": "true"}
        
        with open(excel_path, 'rb') as excel, open(config_path, 'rb') as config:
            files = {
                'excel_file': (os.path.basename(excel_path), excel),
                'config': (os.path.basename(config_path), config)
            }
            data = {'email': self.email}
            
            response = requests.post(url, params=params, files=files, data=data)
            if response.status_code == 202:
                result = response.json()
                session = {
                    'id': result['session_id'],
                    'name': name or os.path.basename(excel_path),
                    'status': 'queued',
                    'started': datetime.now()
                }
                self.sessions.append(session)
                return session
            else:
                print(f"Error starting validation for {excel_path}: {response.json()}")
                return None
    
    def check_status(self, session_id):
        """Check status of a validation session"""
        url = f"{self.base_url}/status/{session_id}"
        response = requests.get(url)
        return response.json()
    
    def wait_for_all(self, check_interval=30):
        """Wait for all validations to complete"""
        print(f"\nMonitoring {len(self.sessions)} validation sessions...")
        
        while True:
            incomplete = 0
            
            for session in self.sessions:
                if session['status'] in ['completed', 'failed']:
                    continue
                
                status = self.check_status(session['id'])
                session['status'] = status['status']
                
                if status['status'] == 'completed':
                    session['completed'] = datetime.now()
                    session['result'] = status.get('result_s3_key')
                    print(f"✅ {session['name']} completed")
                elif status['status'] == 'failed':
                    session['error'] = status.get('error', 'Unknown error')
                    print(f"❌ {session['name']} failed: {session['error']}")
                else:
                    incomplete += 1
            
            if incomplete == 0:
                break
            
            print(f"⏳ {incomplete} validations still running...")
            time.sleep(check_interval)
        
        print("\n📊 Summary:")
        for session in self.sessions:
            print(f"- {session['name']}: {session['status']}")
    
    def process_directory(self, directory, config_file):
        """Process all Excel files in a directory"""
        excel_files = glob.glob(os.path.join(directory, "*.xlsx"))
        
        for excel_file in excel_files:
            name = os.path.splitext(os.path.basename(excel_file))[0]
            self.validate_file(excel_file, config_file, name)
        
        self.wait_for_all()

# Use it
validator = PerplexityValidator(
    "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod",
    "team@company.com"
)

# Single file
validator.validate_file("data.xlsx", "config.json")
validator.wait_for_all()

# Directory of files
validator.process_directory("./excel_files/", "./configs/standard_config.json")
```

## Example 6: Error Handling

Comprehensive error handling example.

```python
import requests
from requests.exceptions import RequestException

def safe_validate(excel_path, config_path, email, max_retries=3):
    url = "https://a0tk95o95g.execute-api.us-east-1.amazonaws.com/prod/validate"
    params = {"preview_first_row": "true"}
    
    for attempt in range(max_retries):
        try:
            with open(excel_path, 'rb') as excel, open(config_path, 'rb') as config:
                files = {
                    'excel_file': (excel_path, excel),
                    'config': (config_path, config)
                }
                data = {'email': email}
                
                response = requests.post(
                    url, 
                    params=params, 
                    files=files, 
                    data=data,
                    timeout=60
                )
                
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 400:
                    error = response.json()
                    print(f"Validation error: {error.get('message', 'Invalid input')}")
                    return None
                elif response.status_code == 504:
                    print("Gateway timeout - switching to async mode")
                    params['async'] = 'true'
                    continue
                else:
                    print(f"Unexpected status: {response.status_code}")
                    print(response.text)
                    
        except FileNotFoundError as e:
            print(f"File not found: {e}")
            return None
        except RequestException as e:
            print(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None
    
    print("Max retries exceeded")
    return None

# Use it with proper error handling
result = safe_validate('data.xlsx', 'config.json', 'user@example.com')
if result:
    print("Validation successful!")
    print(json.dumps(result, indent=2))
```

## Response Formats

### Success Response (Sync)
```json
{
  "statusCode": 200,
  "session_id": "20250701123456_abc123",
  "preview_results": {
    "results": {},
    "summary": {}
  }
}
```

### Success Response (Async)
```json
{
  "statusCode": 202,
  "message": "Validation job queued",
  "session_id": "20250701123456_abc123",
  "reference_pin": "ABC123"
}
```

### Error Response
```json
{
  "statusCode": 400,
  "error": "ValidationError",
  "message": "Column 'Product Name' not found in Excel file",
  "details": {
    "missing_columns": ["Product Name"],
    "available_columns": ["Item", "Description", "Price"]
  }
}
```

### Status Response
```json
{
  "session_id": "20250701123456_abc123",
  "status": "processing",
  "created_at": "2025-07-01T12:34:56Z",
  "progress": {
    "processed_rows": 45,
    "total_rows": 100,
    "percentage": 45
  }
}
``` 