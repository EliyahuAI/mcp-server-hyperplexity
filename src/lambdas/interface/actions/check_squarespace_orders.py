"""
Smart Squarespace order checking - triggered on-demand.
"""

import json
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def handle(request_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle check for new Squarespace orders for a specific user."""
    try:
        from .squarespace_order_poller import poll_squarespace_orders, process_credit_order
        from interface_lambda.utils.helpers import create_response
        import os
        import requests
        
        email = request_data.get('email', '').lower().strip()
        if not email:
            return create_response(400, {'error': 'Email required'})
        
        # Get API key from SSM
        from .squarespace_order_poller import get_squarespace_api_key
        api_key = get_squarespace_api_key()
        if not api_key:
            logger.warning("SQUARESPACE_API_KEY not available - manual credit addition only")
            return create_response(200, {
                'success': True,
                'message': 'Order checking not configured. Please contact support if you made a purchase.',
                'manual_mode': True
            })
        
        # Check for recent orders for this email (last 2 hours for better coverage)
        since_time = (datetime.utcnow() - timedelta(hours=2)).isoformat() + 'Z'
        
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'Hyperplexity/1.0',
            'Content-Type': 'application/json'
        }
        
        # Query Squarespace for orders by email
        params = {
            'modifiedAfter': since_time,
            'customerEmail': email  # Filter by customer email
        }
        
        try:
            response = requests.get(
                "https://api.squarespace.com/1.0/commerce/orders",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 401:
                logger.error("Invalid Squarespace API key")
                return create_response(200, {
                    'success': True,
                    'message': 'Order checking temporarily unavailable',
                    'orders_checked': 0
                })
            
            if response.status_code != 200:
                logger.error(f"Squarespace API error: {response.status_code}")
                return create_response(200, {
                    'success': True,
                    'message': 'Could not check orders at this time',
                    'orders_checked': 0
                })
            
            orders = response.json().get('result', [])
            processed_count = 0
            new_credits = 0
            
            # Check each order
            for order in orders:
                # Only process fulfilled orders
                if order.get('fulfillmentStatus') != 'FULFILLED':
                    continue
                
                # Check if it's a credit purchase
                is_credit = False
                for item in order.get('lineItems', []):
                    product_name = item.get('productName', '').lower()
                    if any(keyword in product_name for keyword in ['credit', 'hyperplexity']):
                        is_credit = True
                        break
                
                if is_credit:
                    result = process_credit_order(order)
                    if result.get('success') and result.get('amount_added', 0) > 0:
                        processed_count += 1
                        new_credits += result.get('amount_added', 0)
            
            # Return result
            if new_credits > 0:
                return create_response(200, {
                    'success': True,
                    'message': f'Found and processed {processed_count} credit purchase(s)',
                    'credits_added': new_credits,
                    'orders_checked': len(orders),
                    'balance_updated': True
                })
            else:
                return create_response(200, {
                    'success': True,
                    'message': 'No new credit purchases found',
                    'orders_checked': len(orders),
                    'balance_updated': False
                })
                
        except requests.exceptions.Timeout:
            logger.error("Squarespace API timeout")
            return create_response(200, {
                'success': True,
                'message': 'Order check timed out. Please try again.',
                'orders_checked': 0
            })
        except Exception as e:
            logger.error(f"Error checking Squarespace orders: {e}")
            return create_response(200, {
                'success': True,
                'message': 'Could not check orders. Please try again.',
                'orders_checked': 0
            })
            
    except Exception as e:
        logger.error(f"Error in check_squarespace_orders: {str(e)}")
        return create_response(500, {'error': 'Internal error'})