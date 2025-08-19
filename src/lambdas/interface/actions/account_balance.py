"""
Account balance management action handler.
Provides account balance information and handles balance-related operations.
"""
import logging
from decimal import Decimal
from interface_lambda.utils.helpers import create_response

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(request_data, context):
    """Handle account balance requests."""
    logger.info(f"[ACCOUNT_BALANCE] Starting handle with request_data: {request_data}")
    
    try:
        # Import here to avoid circular dependencies
        logger.info("[ACCOUNT_BALANCE] Attempting to import from dynamodb_schemas...")
        try:
            from dynamodb_schemas import (
                check_user_balance, get_domain_multiplier, 
                get_user_transactions, initialize_user_account
            )
            logger.info("[ACCOUNT_BALANCE] Successfully imported dynamodb_schemas functions")
        except ImportError as e:
            logger.error(f"[ACCOUNT_BALANCE] Failed to import dynamodb_schemas: {e}")
            # Return proper CORS response even on import error
            return create_response(500, {
                'error': 'Internal configuration error',
                'details': 'Failed to import required modules',
                'success': False
            })
        
        email = request_data.get('email', '').lower().strip()
        if not email:
            logger.warning("[ACCOUNT_BALANCE] No email provided in request")
            return create_response(400, {'error': 'Email address is required', 'success': False})
        
        logger.info(f"[ACCOUNT_BALANCE] Processing account balance request for {email}")
        
        # Check if user account exists, initialize if needed
        try:
            current_balance = check_user_balance(email)
            if current_balance is None:
                logger.info(f"[ACCOUNT_BALANCE] Initializing new account for {email}")
                initialize_user_account(email)
                current_balance = Decimal('0')
            logger.info(f"[ACCOUNT_BALANCE] Current balance for {email}: {current_balance}")
        except Exception as e:
            logger.error(f"[ACCOUNT_BALANCE] Error checking/initializing balance: {e}")
            return create_response(500, {
                'error': 'Failed to check account balance',
                'details': str(e),
                'success': False
            })
        
        # Get domain multiplier for cost calculations
        email_domain = email.split('@')[-1] if '@' in email else 'unknown'
        try:
            domain_multiplier = get_domain_multiplier(email_domain)
            logger.info(f"[ACCOUNT_BALANCE] Domain multiplier for {email_domain}: {domain_multiplier}")
        except Exception as e:
            logger.warning(f"[ACCOUNT_BALANCE] Could not get domain multiplier: {e}")
            domain_multiplier = Decimal('1')
        
        # Get recent transactions (last 10)
        try:
            recent_transactions = get_user_transactions(email, limit=10)
        except Exception as e:
            logger.warning(f"Could not fetch transactions: {e}")
            recent_transactions = []
        
        # Convert Decimal to float for JSON serialization
        balance_info = {
            'email': email,
            'current_balance': float(current_balance),
            'email_domain': email_domain,
            'recent_transactions': []
        }
        
        # Format recent transactions
        for tx in recent_transactions:
            transaction = {
                'timestamp': tx.get('timestamp', ''),
                'amount': float(tx.get('amount', 0)),
                'balance_after': float(tx.get('balance_after', 0)),
                'transaction_type': tx.get('transaction_type', ''),
                'description': tx.get('description', ''),
                'session_id': tx.get('session_id')
            }
            
            # Add validation-specific fields if present
            if tx.get('raw_cost'):
                transaction['raw_cost'] = float(tx['raw_cost'])
            if tx.get('multiplier_applied'):
                transaction['multiplier_applied'] = float(tx['multiplier_applied'])
                
            balance_info['recent_transactions'].append(transaction)
        
        logger.info(f"Account balance for {email}: ${current_balance}, multiplier: {domain_multiplier}x")
        
        return create_response(200, {
            'success': True,
            'account_info': balance_info,
            'message': 'Account balance retrieved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error processing account balance request: {e}")
        return create_response(500, {
            'error': 'Failed to retrieve account balance',
            'details': str(e)
        })

def handle_add_credits(request_data, context):
    """Handle adding credits to account (admin function)."""
    try:
        from dynamodb_schemas import add_to_balance
        
        email = request_data.get('email', '').lower().strip()
        amount = request_data.get('amount')
        admin_key = request_data.get('admin_key')
        
        if not email or not amount:
            return create_response(400, {'error': 'Email and amount are required'})
        
        # Simple admin key check (in production, use proper authentication)
        if admin_key != 'admin123':  # This should be an environment variable
            return create_response(403, {'error': 'Unauthorized'})
        
        try:
            amount_decimal = Decimal(str(amount))
            if amount_decimal <= 0:
                return create_response(400, {'error': 'Amount must be positive'})
        except (ValueError, TypeError):
            return create_response(400, {'error': 'Invalid amount format'})
        
        # Add to balance
        success = add_to_balance(
            email=email,
            amount=amount_decimal,
            transaction_type='admin_credit',
            description=f'Credits added via API by admin',
            payment_id=None
        )
        
        if success:
            # Get updated balance
            from dynamodb_schemas import check_user_balance
            new_balance = check_user_balance(email)
            
            logger.info(f"Added ${amount_decimal} to {email}, new balance: ${new_balance}")
            
            return create_response(200, {
                'success': True,
                'message': f'Added ${float(amount_decimal):.4f} to account',
                'new_balance': float(new_balance) if new_balance else 0
            })
        else:
            return create_response(500, {'error': 'Failed to add credits to account'})
            
    except Exception as e:
        logger.error(f"Error adding credits: {e}")
        return create_response(500, {
            'error': 'Failed to add credits',
            'details': str(e)
        })