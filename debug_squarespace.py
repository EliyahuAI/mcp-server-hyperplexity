#!/usr/bin/env python3
"""
Local debugging script for Squarespace API integration.
Run this script to test the Squarespace API connectivity and order fetching.
"""

import json
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List

# Set your API key here
SQUARESPACE_API_KEY = "ab22f4ad-2631-4f5b-939f-3c9ae4c470b6"
SQUARESPACE_API_URL = "https://api.squarespace.com/1.0/commerce/orders"

def test_api_connectivity():
    """Test basic API connectivity and authentication."""
    print("[SUCCESS] Testing Squarespace API connectivity...")
    
    headers = {
        'Authorization': f'Bearer {SQUARESPACE_API_KEY}',
        'User-Agent': 'Hyperplexity/1.0',
        'Content-Type': 'application/json'
    }
    
    try:
        # Test with minimal params - get orders from last 24 hours
        now = datetime.now(timezone.utc)
        since_time = (now - timedelta(hours=24)).isoformat().replace('+00:00', 'Z')
        until_time = now.isoformat().replace('+00:00', 'Z')
        
        params = {
            'modifiedAfter': since_time,
            'modifiedBefore': until_time,
            'limit': 10
        }
        
        print(f"[INFO] Fetching orders from: {since_time} to: {until_time}")
        response = requests.get(SQUARESPACE_API_URL, headers=headers, params=params, timeout=10)
        
        print(f"[INFO] Response status: {response.status_code}")
        print(f"[INFO] Response headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            data = response.json()
            orders = data.get('result', [])
            print(f"[SUCCESS] Retrieved {len(orders)} orders")
            
            if orders:
                print("\n[INFO] Sample order structure (showing all fields):")
                sample_order = orders[0]
                
                # Show complete order structure with focus on email fields
                print(json.dumps(sample_order, indent=2, default=str))
                
                # Specifically highlight email-related fields
                print("\n[INFO] EMAIL FIELD ANALYSIS:")
                print(f"  customerEmail: {sample_order.get('customerEmail')}")
                print(f"  verifiedEmail: {sample_order.get('verifiedEmail')}")
                print(f"  verified_email: {sample_order.get('verified_email')}")
                print(f"  alternativeEmail: {sample_order.get('alternativeEmail')}")
                print(f"  alternative_email: {sample_order.get('alternative_email')}")
                
                # Check billing address
                billing_addr = sample_order.get('billingAddress', {})
                print(f"  billingAddress.email: {billing_addr.get('email')}")
                
                # Check form submissions for custom fields
                form_submissions = sample_order.get('formSubmission', [])
                print(f"  formSubmission count: {len(form_submissions)}")
                if form_submissions:
                    print("  formSubmission fields:")
                    for i, field in enumerate(form_submissions):
                        label = field.get('label', '')
                        value = field.get('value', '')
                        field_type = field.get('type', '')
                        print(f"    [{i}] {label} ({field_type}): {value}")
                        
                        # Highlight potential email fields
                        if 'email' in label.lower() or 'verified' in label.lower():
                            print(f"         ^^^ POTENTIAL EMAIL FIELD ^^^")
                
                # Show line items for first order
                if sample_order.get('lineItems'):
                    print("\n[INFO] Line items in first order:")
                    for i, item in enumerate(sample_order.get('lineItems', [])[:3]):
                        print(f"  Item {i+1}:")
                        print(f"    Product: {item.get('productName', 'N/A')}")
                        print(f"    SKU: {item.get('sku', 'N/A')}")
                        print(f"    Quantity: {item.get('quantity', 'N/A')}")
                        print(f"    Unit Price: {item.get('unitPricePaid', {}).get('value', 'N/A')}")
            else:
                print("[INFO] No orders found in the last 24 hours")
                
        elif response.status_code == 401:
            print("[ERROR] Authentication failed - check API key")
            print(f"[ERROR] Response: {response.text}")
        else:
            print(f"[ERROR] API request failed: {response.status_code}")
            print(f"[ERROR] Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("[ERROR] Request timed out")
    except requests.exceptions.ConnectionError:
        print("[ERROR] Connection error")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")

def test_order_filtering(email: str = "elliotgreenblatt@gmail.com"):
    """Test filtering orders by email."""
    if not email:
        print("[INFO] Skipping email filter test")
        return
    
    print(f"\n[SUCCESS] Testing order filtering for email: {email}")
    
    headers = {
        'Authorization': f'Bearer {SQUARESPACE_API_KEY}',
        'User-Agent': 'Hyperplexity/1.0',
        'Content-Type': 'application/json'
    }
    
    # Search orders from last 7 days
    now = datetime.now(timezone.utc)
    since_time = (now - timedelta(days=7)).isoformat().replace('+00:00', 'Z')
    until_time = now.isoformat().replace('+00:00', 'Z')
    
    params = {
        'modifiedAfter': since_time,
        'modifiedBefore': until_time,
        'customerEmail': email,
        'limit': 50
    }
    
    try:
        response = requests.get(SQUARESPACE_API_URL, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            orders = data.get('result', [])
            print(f"[SUCCESS] Found {len(orders)} orders for {email}")
            
            credit_orders = []
            for order in orders:
                # Check if it's a credit purchase
                for item in order.get('lineItems', []):
                    product_name = item.get('productName', '').lower()
                    if any(keyword in product_name for keyword in ['credit', 'hyperplexity']):
                        credit_orders.append(order)
                        break
            
            print(f"[INFO] Found {len(credit_orders)} credit orders")
            
            for i, order in enumerate(credit_orders[:3]):  # Show first 3 credit orders
                print(f"\n[INFO] Credit Order {i+1}:")
                print(f"  ID: {order.get('id')}")
                print(f"  Status: {order.get('fulfillmentStatus')}")
                print(f"  Total: ${order.get('grandTotal', {}).get('value', 'N/A')}")
                print(f"  Date: {order.get('createdOn')}")
                
                # EMAIL FIELD EXTRACTION TEST
                print("  EMAIL FIELDS:")
                print(f"    customerEmail: {order.get('customerEmail')}")
                print(f"    verifiedEmail: {order.get('verifiedEmail')}")
                print(f"    alternativeEmail: {order.get('alternativeEmail')}")
                print(f"    billingAddress.email: {order.get('billingAddress', {}).get('email')}")
                
                # Test our extraction functions
                extracted_verified = extract_verified_email_from_order(order)
                extracted_alternative = extract_alternative_email_from_order(order)
                
                print(f"    EXTRACTED verified_email: {extracted_verified}")
                print(f"    EXTRACTED alternative_email: {extracted_alternative}")
                
                print("  Items:")
                for item in order.get('lineItems', []):
                    print(f"    - {item.get('productName')} (${item.get('unitPricePaid', {}).get('value', 'N/A')})")
                
                # Show complete order structure for detailed analysis
                if i == 0:  # Show full structure for first order only
                    print("\n  [DEBUG] COMPLETE ORDER STRUCTURE:")
                    print(json.dumps(order, indent=4, default=str))
                    
        else:
            print(f"[ERROR] Failed to filter orders: {response.status_code}")
            print(f"[ERROR] Response: {response.text}")
            
    except Exception as e:
        print(f"[ERROR] Error filtering orders: {e}")

def extract_verified_email_from_order(order: Dict[str, Any]) -> str:
    """Test function to extract Verified Email field from Squarespace order."""
    try:
        # Check direct field first
        verified_email = order.get('verifiedEmail') or order.get('verified_email')
        if verified_email:
            return verified_email.lower().strip()
        
        # Check line item customizations (this is where Squarespace stores custom product fields)
        line_items = order.get('lineItems', [])
        if line_items:  # Make sure line_items is not None
            for item in line_items or []:
                customizations = item.get('customizations', [])
                if customizations:  # Make sure customizations is not None
                    for customization in customizations or []:
                        label = customization.get('label', '').lower()
                        if 'verified' in label and 'email' in label:
                            value = customization.get('value', '').strip()
                            if value:
                                print(f"    [DEBUG] Found verified email in customizations: {value}")
                                return value.lower()
        
        # Check custom form submissions
        form_submissions = order.get('formSubmission', [])
        for field in form_submissions:
            label = field.get('label', '').lower()
            if 'verified' in label and 'email' in label:
                value = field.get('value', '').strip()
                if value:
                    print(f"    [DEBUG] Found verified email in form submission: {value}")
                    return value.lower()
        
        return None
        
    except Exception as e:
        return f"ERROR: {e}"

def extract_alternative_email_from_order(order: Dict[str, Any]) -> str:
    """Test function to extract Alternative Email field from Squarespace order."""
    try:
        # Check direct field first
        alt_email = order.get('alternativeEmail') or order.get('alternative_email')
        if alt_email:
            return alt_email.lower().strip()
        
        # Check line item customizations for alternative email fields
        line_items = order.get('lineItems', [])
        if line_items:  # Make sure line_items is not None
            for item in line_items or []:
                customizations = item.get('customizations', [])
                if customizations:  # Make sure customizations is not None
                    for customization in customizations or []:
                        label = customization.get('label', '').lower()
                        if any(keyword in label for keyword in ['alternative', 'alternate', 'backup', 'secondary']):
                            if 'email' in label:
                                value = customization.get('value', '').strip()
                                if value:
                                    print(f"    [DEBUG] Found alternative email in customizations: {value}")
                                    return value.lower()
        
        # Check billing address email as fallback
        billing_email = order.get('billingAddress', {}).get('email')
        if billing_email:
            return billing_email.lower().strip()
        
        # Check form submissions for "Email to fund" or similar fields
        form_submissions = order.get('formSubmission', [])
        for field in form_submissions:
            label = field.get('label', '').lower()
            value = field.get('value', '').strip()
            
            # Check for specific labels that indicate funding email
            if 'email to fund' in label or ('fund' in label and 'email' in label):
                if value:
                    print(f"    [DEBUG] Found funding email in form submission: {value}")
                    return value.lower()
            
            # Check for general alternative email patterns
            if any(keyword in label for keyword in ['alternative', 'alternate', 'backup', 'secondary']):
                if 'email' in label and value:
                    print(f"    [DEBUG] Found alternative email in form submission: {value}")
                    return value.lower()
        
        return None
        
    except Exception as e:
        return f"ERROR: {e}"

def test_credit_detection():
    """Test credit order detection logic."""
    print("\n[SUCCESS] Testing credit order detection...")
    
    # Test product names that should be detected as credits
    test_products = [
        "10 Hyperplexity Credits",
        "Hyperplexity Validation Credits",
        "Credit Package - 25 Credits",
        "Data Validation Credits",
        "Regular Product",
        "Another Non-Credit Item"
    ]
    
    for product in test_products:
        is_credit = any(keyword in product.lower() for keyword in ['credit', 'hyperplexity', 'validation'])
        status = "[SUCCESS]" if is_credit else "[INFO]"
        print(f"{status} '{product}' -> Credit product: {is_credit}")

def test_email_extraction():
    """Test email extraction with sample order data."""
    print("\n[SUCCESS] Testing email extraction logic...")
    
    # Sample order with various email field scenarios
    test_orders = [
        {
            'id': 'test1',
            'customerEmail': 'customer@example.com',
            'verifiedEmail': 'verified@example.com',
            'alternativeEmail': 'alt@example.com'
        },
        {
            'id': 'test2', 
            'customerEmail': 'customer2@example.com',
            'billingAddress': {'email': 'billing@example.com'},
            'formSubmission': [
                {'label': 'Verified Email Address', 'value': 'form-verified@example.com'},
                {'label': 'Alternative Contact Email', 'value': 'form-alt@example.com'}
            ]
        },
        {
            'id': 'test3',
            'customerEmail': 'customer3@example.com'
        }
    ]
    
    for i, order in enumerate(test_orders):
        print(f"\n  Test Order {i+1} (ID: {order['id']}):")
        print(f"    Customer Email: {order.get('customerEmail')}")
        print(f"    Extracted Verified: {extract_verified_email_from_order(order)}")
        print(f"    Extracted Alternative: {extract_alternative_email_from_order(order)}")
        
        # Show what our priority logic would choose
        email_candidates = []
        
        verified = extract_verified_email_from_order(order)
        if verified:
            email_candidates.append(('verified_email', verified))
            
        alternative = extract_alternative_email_from_order(order)
        if alternative:
            email_candidates.append(('alternative_email', alternative))
            
        customer = order.get('customerEmail', '').lower().strip()
        if customer:
            email_candidates.append(('customer_email', customer))
        
        print(f"    Priority Order: {email_candidates}")
        if email_candidates:
            print(f"    WOULD USE: {email_candidates[0][1]} (via {email_candidates[0][0]})")
        else:
            print(f"    WOULD USE: None - ORDER WOULD BE PENDING")

if __name__ == "__main__":
    print("=== Squarespace API Debug Tool ===")
    print(f"API Key: {SQUARESPACE_API_KEY[:8]}...")
    print(f"API URL: {SQUARESPACE_API_URL}")
    print()
    
    # Run tests
    test_api_connectivity()
    test_order_filtering()
    test_credit_detection()
    test_email_extraction()
    
    print("\n=== Debug Complete ===")