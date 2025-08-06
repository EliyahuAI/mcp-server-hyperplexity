"""
Handles WebSocket lifecycle events from API Gateway.
"""
import json
import logging
import sys
from pathlib import Path

from src.shared.dynamodb_schemas import add_websocket_connection, remove_websocket_connection, associate_session_with_connection

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handle(event, context):
    """
    Handles WebSocket connect, disconnect, and message events.
    """
    connection_id = event['requestContext'].get('connectionId')
    route_key = event['requestContext'].get('routeKey')
    
    logger.info(f"🔌 WebSocket Event: connection={connection_id}, route={route_key}")
    logger.info(f"📡 Full event: {json.dumps(event, default=str)}")

    if route_key == '$connect':
        logger.info(f"🟢 WebSocket connecting: {connection_id}")
        try:
            add_websocket_connection(connection_id)
            logger.info(f"✅ WebSocket connection {connection_id} added to database")
            return {'statusCode': 200, 'body': 'Connected.'}
        except Exception as e:
            logger.error(f"❌ Failed to add WebSocket connection {connection_id}: {e}")
            return {'statusCode': 500, 'body': 'Failed to connect.'}
        
    elif route_key == '$disconnect':
        logger.info(f"🔴 WebSocket disconnecting: {connection_id}")
        try:
            remove_websocket_connection(connection_id)
            logger.info(f"✅ WebSocket connection {connection_id} removed from database")
            return {'statusCode': 200, 'body': 'Disconnected.'}
        except Exception as e:
            logger.error(f"❌ Failed to remove WebSocket connection {connection_id}: {e}")
            return {'statusCode': 500, 'body': 'Failed to disconnect.'}
        
    elif route_key == 'subscribe':
        logger.info(f"📝 WebSocket subscribe request from {connection_id}")
        try:
            body = json.loads(event.get('body', '{}'))
            session_id = body.get('sessionId')
            logger.info(f"📋 Subscribe body: {body}")
            logger.info(f"🎯 Session ID: {session_id}")
            
            if session_id:
                associate_session_with_connection(connection_id, session_id)
                logger.info(f"✅ Connection {connection_id} successfully subscribed to session {session_id}")
                return {'statusCode': 200, 'body': 'Subscribed.'}
            else:
                logger.warning(f"❌ No sessionId provided in subscribe message")
                return {'statusCode': 400, 'body': 'sessionId not provided in subscribe message.'}
        except Exception as e:
            logger.error(f"❌ Error handling subscribe message from {connection_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'statusCode': 500, 'body': 'Internal server error.'}
            
    else:
        # Default route
        logger.warning(f"❓ Unhandled route key: {route_key} for connection {connection_id}")
        return {'statusCode': 404, 'body': 'Not Found'} 