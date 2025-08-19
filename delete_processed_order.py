#!/usr/bin/env python3
"""
Delete processed order marker so order can be reprocessed with correct amount.
"""

import boto3
import sys

def delete_processed_order_marker(order_id):
    """Delete the processed marker for a specific order."""
    try:
        s3_client = boto3.client('s3')
        bucket_name = 'hyperplexity-storage'
        key = f"payments/processed/squarespace_{order_id}.json"
        
        print(f"Deleting processed marker: s3://{bucket_name}/{key}")
        
        # Check if the object exists first
        try:
            s3_client.head_object(Bucket=bucket_name, Key=key)
            print("[SUCCESS] Found processed marker")
        except Exception:
            print("[INFO] Processed marker not found - order can already be reprocessed")
            return True
        
        # Delete the object
        s3_client.delete_object(Bucket=bucket_name, Key=key)
        print("[SUCCESS] Processed marker deleted successfully")
        
        # Verify deletion
        try:
            s3_client.head_object(Bucket=bucket_name, Key=key)
            print("[ERROR] Failed to delete processed marker - object still exists")
            return False
        except Exception:  # Any exception (404, etc.) means object is gone
            print("[SUCCESS] Deletion confirmed")
            return True
            
    except Exception as e:
        print(f"[ERROR] Error deleting processed marker: {e}")
        return False

if __name__ == "__main__":
    order_id = "68a38b2816ca922f67e763a3"
    print(f"Deleting processed marker for order: {order_id}")
    
    success = delete_processed_order_marker(order_id)
    
    if success:
        print("\n[SUCCESS] Order can now be reprocessed with correct amount!")
        print("Run checkForNewOrders() in the frontend console to reprocess.")
    else:
        print("\n[ERROR] Failed to delete processed marker")
        sys.exit(1)