"""
WebSocket client for sending messages from validation lambda to connected clients
"""
import boto3
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class WebSocketClient:
    """Client for sending WebSocket messages to connected clients"""
    
    def __init__(self):
        self.websocket_url = os.environ.get('WEBSOCKET_API_URL', '')
        logger.debug(f"Initializing WebSocketClient with URL: {self.websocket_url}")
        
        # Extract API Gateway info from WebSocket URL
        if self.websocket_url.startswith('wss://'):
            # Format: wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod
            parts = self.websocket_url.replace('wss://', '').split('/')
            if len(parts) >= 2:
                self.api_id = parts[0].split('.')[0]
                self.stage = parts[1]
                endpoint_url = f'https://{parts[0]}/{self.stage}'
                logger.debug(f"Creating API Gateway Management client with endpoint: {endpoint_url}")
                
                # Create API Gateway Management API client
                self.client = boto3.client(
                    'apigatewaymanagementapi',
                    endpoint_url=endpoint_url,
                    region_name='us-east-1'
                )
                logger.debug("WebSocketClient initialized successfully")
            else:
                logger.error(f"Invalid WebSocket URL format: {self.websocket_url}")
                self.client = None
        else:
            logger.error(f"Invalid WebSocket URL: {self.websocket_url}")
            self.client = None
    
    def send_to_session(self, session_id: str, message: Dict[str, Any]) -> bool:
        """
        Send a message to all connections subscribed to a session
        
        Args:
            session_id: The session ID to send the message to
            message: The message data to send
            
        Returns:
            bool: True if message was sent successfully
        """
        if not self.client:
            logger.error("WebSocket client not initialized")
            return False
        
        try:
            # Get connections for this session
            connections = self._get_connections_for_session(session_id)
            
            if not connections:
                logger.warning(f"No WebSocket connections found for session {session_id}")
                return False
            
            # Send message to all connections
            success_count = 0
            for connection_id in connections:
                if self._send_to_connection(connection_id, message):
                    success_count += 1
            
            logger.debug(f"Sent WebSocket message to {success_count}/{len(connections)} connections for session {session_id}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error sending WebSocket message to session {session_id}: {e}")
            return False
    
    def _get_connections_for_session(self, session_id: str) -> list:
        """Get all connection IDs subscribed to a session"""
        try:
            from dynamodb_schemas import get_connections_for_session
            return get_connections_for_session(session_id)
        except ImportError as e:
            logger.error(f"Failed to import dynamodb_schemas for session {session_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting connections for session {session_id}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return []
    
    def _send_to_connection(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """Send a message to a specific connection"""
        try:
            self.client.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(message)
            )
            return True
        except self.client.exceptions.GoneException:
            # Connection is stale, remove it
            logger.info(f"Connection {connection_id} is stale, removing")
            try:
                from dynamodb_schemas import remove_websocket_connection
                remove_websocket_connection(connection_id)
            except ImportError as e:
                logger.error(f"Failed to import dynamodb_schemas for removing connection {connection_id}: {e}")
            except Exception as e:
                logger.warning(f"Failed to remove stale connection {connection_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending to connection {connection_id}: {e}")
            return False
    
    def send_config_generation_result(self, session_id: str, success: bool, 
                                    generated_config: Optional[Dict[str, Any]] = None,
                                    ai_response: str = "",
                                    error_message: str = "",
                                    download_url: str = "") -> bool:
        """
        Send a config generation result via WebSocket
        
        Args:
            session_id: Session ID to send to
            success: Whether the config generation was successful
            generated_config: The generated configuration (if successful)
            ai_response: AI response text
            error_message: Error message (if failed)
            download_url: S3 download URL for the config file
            
        Returns:
            bool: True if message was sent successfully
        """
        if success:
            message = {
                'status': 'COMPLETED',
                'type': 'config_generation_complete',
                'session_id': session_id,
                'success': True,
                'generated_config': generated_config,
                'ai_response': ai_response,
                'download_url': download_url,
                'timestamp': datetime.now().isoformat()
            }
        else:
            message = {
                'status': 'FAILED',
                'type': 'config_generation_failed',
                'session_id': session_id,
                'success': False,
                'error': error_message,
                'timestamp': datetime.now().isoformat()
            }
        
        return self.send_to_session(session_id, message)

# Global instance
websocket_client = WebSocketClient()