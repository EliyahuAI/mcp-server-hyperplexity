"""
WebSocket client for sending messages from validation lambda to connected clients
"""
import boto3
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class WebSocketClient:
    """Client for sending WebSocket messages to connected clients"""

    def __init__(self):
        self.websocket_url = os.environ.get('WEBSOCKET_API_URL', '')
        logger.info(f"[WEBSOCKET_CLIENT] Initializing WebSocketClient with URL: {self.websocket_url}")

        # Sequence counters per session for message ordering
        self._sequence_counters = {}

        # Extract API Gateway info from WebSocket URL
        if self.websocket_url.startswith('wss://'):
            # Format: wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod
            parts = self.websocket_url.replace('wss://', '').split('/')
            if len(parts) >= 2:
                self.api_id = parts[0].split('.')[0]
                self.stage = parts[1]
                endpoint_url = f'https://{parts[0]}/{self.stage}'
                logger.info(f"[WEBSOCKET_CLIENT] Creating API Gateway Management client with endpoint: {endpoint_url}")

                # Create API Gateway Management API client
                self.client = boto3.client(
                    'apigatewaymanagementapi',
                    endpoint_url=endpoint_url,
                    region_name='us-east-1'
                )
                logger.info("[WEBSOCKET_CLIENT] WebSocketClient initialized successfully")
            else:
                logger.error(f"[WEBSOCKET_CLIENT] Invalid WebSocket URL format: {self.websocket_url}")
                self.client = None
        else:
            logger.error(f"[WEBSOCKET_CLIENT] Invalid WebSocket URL: {self.websocket_url}")
            self.client = None
    
    def _get_next_sequence(self, session_id: str) -> int:
        """Get next sequence number for session (in-memory counter)"""
        if session_id not in self._sequence_counters:
            self._sequence_counters[session_id] = 0

        self._sequence_counters[session_id] += 1
        return self._sequence_counters[session_id]

    def _persist_message(self, session_id: str, card_id: str, seq: int, message: dict) -> bool:
        """
        Persist message to DynamoDB message log (fire-and-forget, don't block WebSocket send).
        """
        try:
            from dynamodb_schemas import persist_message_to_log
            return persist_message_to_log(session_id, card_id, seq, message)
        except ImportError as e:
            logger.warning(f"[WEBSOCKET_CLIENT] Could not import persist_message_to_log: {e}")
            return False
        except Exception as e:
            logger.error(f"[WEBSOCKET_CLIENT] Failed to persist message {seq} for {card_id}: {e}")
            # Don't raise - message already sent via WebSocket
            return False

    def send_to_session(self, session_id: str, message: Dict[str, Any], card_id: str = None) -> bool:
        """
        Send a message to all connections subscribed to a session.
        Optionally persists message to DynamoDB for replay if card_id is provided.

        Args:
            session_id: The session ID to send the message to
            message: The message data to send
            card_id: Optional card identifier for message persistence and replay

        Returns:
            bool: True if message was sent successfully
        """
        if not self.client:
            logger.error("[WEBSOCKET_CLIENT] WebSocket client not initialized")
            return False

        try:
            # Get next sequence number for this session
            seq = self._get_next_sequence(session_id)

            # Add metadata to message
            message_with_meta = {
                **message,
                '_seq': seq,
                '_card_id': card_id,
                '_timestamp': int(time.time() * 1000)
            }

            logger.info(f"[WEBSOCKET_CLIENT] Attempting to send message to session {session_id}, type={message.get('type')}, seq={seq}, card_id={card_id}")

            # Persist to message log if card_id provided (async, non-blocking)
            if card_id:
                self._persist_message(session_id, card_id, seq, message_with_meta)

            # Get connections for this session
            connections = self._get_connections_for_session(session_id)

            if not connections:
                logger.warning(f"[WEBSOCKET_CLIENT] No WebSocket connections found for session {session_id}")
                logger.warning(f"[WEBSOCKET_CLIENT] This means the frontend is not connected or the session ID doesn't match")
                return False

            logger.info(f"[WEBSOCKET_CLIENT] Found {len(connections)} connection(s) for session {session_id}")

            # Send message with metadata to all connections
            success_count = 0
            for connection_id in connections:
                if self._send_to_connection(connection_id, message_with_meta):
                    success_count += 1

            logger.info(f"[WEBSOCKET_CLIENT] Sent WebSocket message to {success_count}/{len(connections)} connections for session {session_id}")
            return success_count > 0

        except Exception as e:
            logger.error(f"[WEBSOCKET_CLIENT] Error sending WebSocket message to session {session_id}: {e}")
            import traceback
            logger.error(f"[WEBSOCKET_CLIENT] Traceback: {traceback.format_exc()}")
            return False
    
    def _get_connections_for_session(self, session_id: str) -> list:
        """Get all connection IDs subscribed to a session"""
        try:
            logger.info(f"[WEBSOCKET_CLIENT] Looking up connections for session: {session_id}")
            from dynamodb_schemas import get_connections_for_session
            connections = get_connections_for_session(session_id)
            logger.info(f"[WEBSOCKET_CLIENT] DynamoDB returned {len(connections)} connection(s) for session {session_id}")
            if connections:
                logger.info(f"[WEBSOCKET_CLIENT] Connection IDs: {connections}")
            return connections
        except ImportError as e:
            logger.error(f"[WEBSOCKET_CLIENT] Failed to import dynamodb_schemas for session {session_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"[WEBSOCKET_CLIENT] Error getting connections for session {session_id}: {e}")
            import traceback
            logger.error(f"[WEBSOCKET_CLIENT] Full traceback: {traceback.format_exc()}")
            return []
    
    def _send_to_connection(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """Send a message to a specific connection"""
        try:
            logger.info(f"[WEBSOCKET_CLIENT] Sending message to connection {connection_id}, type={message.get('type')}")
            self.client.post_to_connection(
                ConnectionId=connection_id,
                Data=json.dumps(message)
            )
            logger.info(f"[WEBSOCKET_CLIENT] Successfully sent message to connection {connection_id}")
            return True
        except self.client.exceptions.GoneException:
            # Connection is stale, remove it
            logger.warning(f"[WEBSOCKET_CLIENT] Connection {connection_id} is stale, removing")
            try:
                from dynamodb_schemas import remove_websocket_connection
                remove_websocket_connection(connection_id)
            except ImportError as e:
                logger.error(f"[WEBSOCKET_CLIENT] Failed to import dynamodb_schemas for removing connection {connection_id}: {e}")
            except Exception as e:
                logger.warning(f"[WEBSOCKET_CLIENT] Failed to remove stale connection {connection_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"[WEBSOCKET_CLIENT] Error sending to connection {connection_id}: {e}")
            import traceback
            logger.error(f"[WEBSOCKET_CLIENT] Traceback: {traceback.format_exc()}")
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

    def send_ticker_update(self, session_id: str, priority: int, row_ids: str,
                          column: str, final_value: str, confidence: str,
                          explanation: str = "") -> bool:
        """
        Send a ticker update notification via WebSocket

        Args:
            session_id: Session ID to send to
            priority: Importance level (4 or 5) for ticker priority
            row_ids: Row identifier(s) (e.g., "Amazon - Home Products")
            column: Column name
            final_value: Final validated value
            confidence: Confidence level (HIGH/MEDIUM/LOW) for emoji selection
            explanation: Importance explanation (optional, for priority tracking)

        Returns:
            bool: True if message was sent successfully
        """
        # Map confidence to emoji
        emoji_map = {
            'HIGH': '🟢',
            'MEDIUM': '🟡',
            'LOW': '🔴'
        }
        confidence_emoji = emoji_map.get(confidence.upper() if confidence else '', '🟢')

        message = {
            'type': 'ticker_update',
            'session_id': session_id,
            'priority': priority,
            'row_ids': row_ids,
            'column': column,
            'final_value': final_value,
            'confidence': confidence,
            'confidence_emoji': confidence_emoji,
            'explanation': explanation,
            'timestamp': datetime.now().isoformat()
        }

        return self.send_to_session(session_id, message)

# Global instance
websocket_client = WebSocketClient()