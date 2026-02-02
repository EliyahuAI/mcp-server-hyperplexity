"""
Security event logging to CloudWatch.

Logs security-related events (violations, rate limits, invalid attempts) to
CloudWatch Logs and Metrics for monitoring and alerting.

Events are logged to both:
1. CloudWatch Logs (for detailed forensics)
2. CloudWatch Metrics (for dashboards and alarms)
"""
import boto3
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
cloudwatch = boto3.client('cloudwatch')


# Security event severity levels
SEVERITY_INFO = 'INFO'
SEVERITY_WARNING = 'WARNING'
SEVERITY_HIGH = 'HIGH'
SEVERITY_CRITICAL = 'CRITICAL'


def log_security_event(
    event_type: str,
    email: Optional[str] = None,
    session_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    severity: str = SEVERITY_INFO,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log security event to CloudWatch Logs and Metrics.

    Args:
        event_type: Type of security event (e.g., 'ownership_violation', 'rate_limit_exceeded')
        email: User's email address (if applicable)
        session_id: Session ID involved (if applicable)
        ip_address: IP address (if applicable)
        severity: Event severity (INFO, WARNING, HIGH, CRITICAL)
        details: Additional event details (dict)

    Event Types:
        - ownership_violation: User attempted to access session they don't own
        - rate_limit_exceeded: User exceeded API rate limit
        - invalid_session_format: Session ID format validation failed
        - path_traversal_attempt: Session ID contained path traversal characters
        - unvalidated_email_access: Unvalidated email attempted to access data
        - ip_rate_limit_exceeded: IP address exceeded rate limit
        - account_locked: Account locked due to too many failed attempts
        - invalid_token: Invalid or expired session token
        - missing_token: No session token provided

    Examples:
        >>> log_security_event('ownership_violation', email='user@test.com',
        ...                    session_id='session_123', severity=SEVERITY_HIGH)

        >>> log_security_event('rate_limit_exceeded', email='spam@test.com',
        ...                    severity=SEVERITY_WARNING, details={'limit': 10})
    """
    try:
        # Create structured log entry
        log_entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'severity': severity,
            'email': email,
            'session_id': session_id,
            'ip_address': ip_address,
            'details': details or {}
        }

        # Log to CloudWatch Logs with structured JSON
        logger.info(f"[SECURITY_EVENT] {json.dumps(log_entry)}")

        # Send CloudWatch Metric for monitoring/alerting
        try:
            metric_data = {
                'MetricName': event_type,
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': datetime.now(timezone.utc),
                'Dimensions': [
                    {'Name': 'Severity', 'Value': severity}
                ]
            }

            # Add email dimension if provided (for per-user tracking)
            if email:
                metric_data['Dimensions'].append({
                    'Name': 'Email',
                    'Value': email[:50]  # Truncate to 50 chars for CloudWatch limits
                })

            cloudwatch.put_metric_data(
                Namespace='Hyperplexity/Security',
                MetricData=[metric_data]
            )

        except Exception as e:
            # Don't fail the request if metric publishing fails
            logger.debug(f"Failed to publish CloudWatch metric: {e}")

    except Exception as e:
        # Logging should never break application flow
        logger.error(f"Failed to log security event: {e}")


def log_ownership_violation(email: str, session_id: str, ip_address: Optional[str] = None) -> None:
    """Log when a user attempts to access a session they don't own."""
    log_security_event(
        event_type='ownership_violation',
        email=email,
        session_id=session_id,
        ip_address=ip_address,
        severity=SEVERITY_HIGH,
        details={'action': 'attempted_unauthorized_access'}
    )


def log_rate_limit_exceeded(email: str, action: str, limit: int, ip_address: Optional[str] = None) -> None:
    """Log when a user exceeds rate limit."""
    log_security_event(
        event_type='rate_limit_exceeded',
        email=email,
        ip_address=ip_address,
        severity=SEVERITY_WARNING,
        details={'action': action, 'limit': limit}
    )


def log_invalid_session_format(session_id: str, email: Optional[str] = None, ip_address: Optional[str] = None) -> None:
    """Log when an invalid session ID format is detected."""
    log_security_event(
        event_type='invalid_session_format',
        email=email,
        session_id=session_id,
        ip_address=ip_address,
        severity=SEVERITY_WARNING,
        details={'attempted_session_id': session_id}
    )


def log_path_traversal_attempt(session_id: str, email: Optional[str] = None, ip_address: Optional[str] = None) -> None:
    """Log when a path traversal attempt is detected in session ID."""
    log_security_event(
        event_type='path_traversal_attempt',
        email=email,
        session_id=session_id,
        ip_address=ip_address,
        severity=SEVERITY_HIGH,
        details={'attempted_session_id': session_id}
    )


def log_unvalidated_email_access(email: str, ip_address: Optional[str] = None) -> None:
    """Log when an unvalidated email attempts to access data."""
    log_security_event(
        event_type='unvalidated_email_access',
        email=email,
        ip_address=ip_address,
        severity=SEVERITY_WARNING,
        details={'action': 'attempted_access_without_validation'}
    )


def log_account_locked(email: str, attempts: int, ip_address: Optional[str] = None) -> None:
    """Log when an account is locked due to too many failed attempts."""
    log_security_event(
        event_type='account_locked',
        email=email,
        ip_address=ip_address,
        severity=SEVERITY_WARNING,
        details={'failed_attempts': attempts, 'lockout_duration_minutes': 15}
    )


def log_invalid_token(email: Optional[str] = None, ip_address: Optional[str] = None, reason: str = None) -> None:
    """Log when an invalid or expired session token is provided."""
    log_security_event(
        event_type='invalid_token',
        email=email,
        ip_address=ip_address,
        severity=SEVERITY_INFO,
        details={'reason': reason}
    )
