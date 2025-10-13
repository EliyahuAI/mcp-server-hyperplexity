#!/usr/bin/env python3
"""
Conversation handler for table generation system.
Main orchestration logic for conversational table design with AI.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

# Configure logging
logger = logging.getLogger(__name__)


class TableConversationHandler:
    """Handle conversational table design with iterative refinement."""

    def __init__(self, ai_client, prompt_loader, schema_validator):
        """
        Initialize conversation handler.

        Args:
            ai_client: AI API client instance (from ../../src/shared/ai_api_client.py)
            prompt_loader: PromptLoader instance
            schema_validator: SchemaValidator instance
        """
        self.ai_client = ai_client
        self.prompt_loader = prompt_loader
        self.schema_validator = schema_validator

        # Conversation state
        self.conversation_log = []
        self.conversation_id = None
        self.current_proposal = None
        self.is_initialized = False

        logger.info("Initialized TableConversationHandler")

    async def start_conversation(
        self,
        user_message: str,
        model: str = "claude-sonnet-4-5",
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initialize conversation with user's research description.

        Args:
            user_message: User's initial research description
            model: AI model to use
            conversation_id: Optional conversation ID (auto-generated if not provided)

        Returns:
            Dictionary with conversation results:
            {
                'success': bool,
                'conversation_id': str,
                'ai_response': Dict,  # Complete AI response
                'ai_message': str,    # Natural language response
                'proposed_table': Dict,
                'ready_to_generate': bool,
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'conversation_id': None,
            'ai_response': None,
            'ai_message': '',
            'proposed_table': None,
            'ready_to_generate': False,
            'error': None
        }

        try:
            # Initialize conversation
            self.conversation_id = conversation_id or self._generate_conversation_id()
            self.conversation_log = []
            self.current_proposal = None
            self.is_initialized = True

            logger.info(
                f"Starting conversation {self.conversation_id}: '{user_message[:50]}...'"
            )

            # Add user message to log
            self._add_message_to_log('user', user_message)

            # Load initial prompt template
            variables = {
                'USER_MESSAGE': user_message
            }
            prompt = self.prompt_loader.load_prompt('table_initial', variables)

            # Load response schema
            schema = self.schema_validator.load_schema('conversation_response')

            # Call AI API (standalone mode - no caching, no debug saves)
            logger.debug(f"Calling AI API with model: {model}")
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=8000,
                use_cache=False,  # Disable caching for standalone mode
                debug_name=None  # Disable debug file saving
            )

            # Check API call success
            if not api_response.get('success'):
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed. Error: {error_detail}")
                logger.error(f"Full API response: {json.dumps(api_response, indent=2)}")
                raise Exception(
                    f"AI API call failed: {error_detail}"
                )

            # Extract and validate response
            ai_response = api_response.get('response', {})
            validation_result = self.schema_validator.validate_ai_response(
                ai_response,
                'conversation_response'
            )

            if not validation_result['is_valid']:
                raise Exception(
                    f"AI response validation failed: {validation_result['errors']}"
                )

            # Store AI response in log
            self._add_message_to_log('assistant', ai_response)

            # Update current proposal
            self.current_proposal = {
                'rows': ai_response.get('proposed_rows', {}),
                'columns': ai_response.get('proposed_columns', [])
            }

            # Build result
            result['success'] = True
            result['conversation_id'] = self.conversation_id
            result['ai_response'] = ai_response
            result['ai_message'] = ai_response.get('ai_message', '')
            result['proposed_table'] = self.current_proposal
            result['ready_to_generate'] = ai_response.get('ready_to_generate', False)

            logger.info(
                f"Conversation started successfully. "
                f"Ready to generate: {result['ready_to_generate']}"
            )

            # Log token usage
            if 'token_usage' in api_response:
                self._log_token_usage(api_response['token_usage'])

        except Exception as e:
            error_msg = f"Error starting conversation: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            self.is_initialized = False

        return result

    async def continue_conversation(
        self,
        user_message: str,
        model: str = "claude-sonnet-4-5"
    ) -> Dict[str, Any]:
        """
        Continue conversation with user feedback.

        Args:
            user_message: User's feedback or refinement request
            model: AI model to use

        Returns:
            Dictionary with conversation results (same structure as start_conversation)
        """
        result = {
            'success': False,
            'conversation_id': self.conversation_id,
            'ai_response': None,
            'ai_message': '',
            'proposed_table': None,
            'ready_to_generate': False,
            'error': None
        }

        try:
            # Check initialization
            if not self.is_initialized:
                raise ValueError(
                    "Conversation not initialized. Call start_conversation first."
                )

            logger.info(
                f"Continuing conversation {self.conversation_id}: '{user_message[:50]}...'"
            )

            # Add user message to log
            self._add_message_to_log('user', user_message)

            # Build conversation history string
            conversation_history = self._format_conversation_history()

            # Format current proposal
            current_proposal_str = json.dumps(self.current_proposal, indent=2)

            # Load refinement prompt template
            variables = {
                'CONVERSATION_HISTORY': conversation_history,
                'CURRENT_PROPOSAL': current_proposal_str,
                'USER_MESSAGE': user_message
            }
            prompt = self.prompt_loader.load_prompt('table_refinement', variables)

            # Load response schema
            schema = self.schema_validator.load_schema('conversation_response')

            # Call AI API (standalone mode - no caching, no debug saves)
            logger.debug(f"Calling AI API with model: {model}")
            api_response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=schema,
                model=model,
                max_tokens=8000,
                use_cache=False,  # Disable caching for standalone mode
                debug_name=None  # Disable debug file saving
            )

            # Check API call success
            if not api_response.get('success'):
                error_detail = api_response.get('error', 'Unknown error')
                logger.error(f"API call failed. Error: {error_detail}")
                logger.error(f"Full API response: {json.dumps(api_response, indent=2)}")
                raise Exception(
                    f"AI API call failed: {error_detail}"
                )

            # Extract and validate response
            ai_response = api_response.get('response', {})
            validation_result = self.schema_validator.validate_ai_response(
                ai_response,
                'conversation_response'
            )

            if not validation_result['is_valid']:
                raise Exception(
                    f"AI response validation failed: {validation_result['errors']}"
                )

            # Store AI response in log
            self._add_message_to_log('assistant', ai_response)

            # Update current proposal
            self.current_proposal = {
                'rows': ai_response.get('proposed_rows', {}),
                'columns': ai_response.get('proposed_columns', [])
            }

            # Build result
            result['success'] = True
            result['ai_response'] = ai_response
            result['ai_message'] = ai_response.get('ai_message', '')
            result['proposed_table'] = self.current_proposal
            result['ready_to_generate'] = ai_response.get('ready_to_generate', False)

            logger.info(
                f"Conversation continued successfully. "
                f"Ready to generate: {result['ready_to_generate']}"
            )

            # Log token usage
            if 'token_usage' in api_response:
                self._log_token_usage(api_response['token_usage'])

        except Exception as e:
            error_msg = f"Error continuing conversation: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Return full conversation log.

        Returns:
            List of conversation messages with metadata
        """
        return list(self.conversation_log)

    def get_current_proposal(self) -> Optional[Dict[str, Any]]:
        """
        Return latest table proposal.

        Returns:
            Current table proposal with rows and columns, or None if not initialized
        """
        return self.current_proposal

    def get_table_structure(self) -> Dict[str, Any]:
        """
        Get finalized table structure for export.

        Returns:
            Complete table structure with metadata
        """
        if not self.current_proposal:
            raise ValueError("No current proposal available")

        # Build table structure
        rows_data = self.current_proposal.get('rows', {})
        columns_data = self.current_proposal.get('columns', [])

        structure = {
            'columns': columns_data,
            'rows': rows_data.get('sample_rows', []),
            'metadata': {
                'created_at': datetime.utcnow().isoformat() + 'Z',
                'conversation_id': self.conversation_id,
                'description': self._extract_research_description(),
                'row_count': len(rows_data.get('sample_rows', [])),
                'column_count': len(columns_data),
                'identification_columns': rows_data.get('identification_columns', []),
                'conversation_turns': len(self.conversation_log)
            }
        }

        return structure

    def is_ready_to_generate(self) -> bool:
        """
        Check if table is ready to be generated.

        Returns:
            True if ready to generate, False otherwise
        """
        if not self.conversation_log:
            return False

        # Check last AI response
        last_message = self._get_last_assistant_message()
        if last_message:
            return last_message.get('ready_to_generate', False)

        return False

    def reset_conversation(self):
        """Reset conversation state."""
        self.conversation_log = []
        self.conversation_id = None
        self.current_proposal = None
        self.is_initialized = False
        logger.info("Conversation reset")

    def save_conversation(self, output_path: str) -> Dict[str, Any]:
        """
        Save conversation to file.

        Args:
            output_path: Path for output file

        Returns:
            Dictionary with save results
        """
        result = {
            'success': False,
            'output_path': output_path,
            'error': None
        }

        try:
            from pathlib import Path

            conversation_data = {
                'conversation_id': self.conversation_id,
                'created_at': self.conversation_log[0]['timestamp'] if self.conversation_log else None,
                'last_updated': self.conversation_log[-1]['timestamp'] if self.conversation_log else None,
                'turn_count': len(self.conversation_log),
                'messages': self.conversation_log,
                'current_proposal': self.current_proposal,
                'ready_to_generate': self.is_ready_to_generate()
            }

            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(conversation_data, f, indent=2, ensure_ascii=False)

            result['success'] = True
            logger.info(f"Saved conversation to: {output_path}")

        except Exception as e:
            error_msg = f"Error saving conversation: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg

        return result

    def load_conversation(self, input_path: str) -> Dict[str, Any]:
        """
        Load conversation from file.

        Args:
            input_path: Path to conversation file

        Returns:
            Dictionary with load results
        """
        result = {
            'success': False,
            'error': None
        }

        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                conversation_data = json.load(f)

            self.conversation_id = conversation_data['conversation_id']
            self.conversation_log = conversation_data['messages']
            self.current_proposal = conversation_data['current_proposal']
            self.is_initialized = True

            result['success'] = True
            logger.info(
                f"Loaded conversation {self.conversation_id} with "
                f"{len(self.conversation_log)} messages"
            )

        except Exception as e:
            error_msg = f"Error loading conversation: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            self.is_initialized = False

        return result

    def _generate_conversation_id(self) -> str:
        """Generate unique conversation ID."""
        return f"table_conv_{uuid.uuid4().hex[:12]}"

    def _add_message_to_log(self, role: str, content: Any):
        """
        Add message to conversation log.

        Args:
            role: 'user' or 'assistant'
            content: Message content (string for user, dict for assistant)
        """
        message = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'role': role,
            'content': content
        }

        self.conversation_log.append(message)
        logger.debug(f"Added {role} message to log (total: {len(self.conversation_log)})")

    def _format_conversation_history(self) -> str:
        """
        Format conversation history for prompt.

        Returns:
            Formatted conversation history string
        """
        history_lines = []

        for idx, msg in enumerate(self.conversation_log[:-1], 1):  # Exclude latest message
            role = msg['role'].upper()
            content = msg['content']

            if role == 'USER':
                history_lines.append(f"Turn {idx} - USER: {content}")
            else:
                # For assistant, show the natural language response
                ai_message = content.get('ai_message', '') if isinstance(content, dict) else content
                history_lines.append(f"Turn {idx} - ASSISTANT: {ai_message}")

        return '\n\n'.join(history_lines) if history_lines else "No previous conversation"

    def _get_last_assistant_message(self) -> Optional[Dict[str, Any]]:
        """
        Get last assistant message from log.

        Returns:
            Last assistant message content or None
        """
        for msg in reversed(self.conversation_log):
            if msg['role'] == 'assistant':
                return msg['content']
        return None

    def _extract_research_description(self) -> str:
        """
        Extract research description from first user message.

        Returns:
            Research description string
        """
        if not self.conversation_log:
            return "No description available"

        first_message = self.conversation_log[0]
        if first_message['role'] == 'user':
            return first_message['content']

        return "No description available"

    def _log_token_usage(self, token_usage: Dict[str, Any]):
        """
        Log token usage information.

        Args:
            token_usage: Token usage dictionary from API response
        """
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        total_tokens = token_usage.get('total_tokens', 0)

        logger.info(
            f"Token usage - Input: {input_tokens}, Output: {output_tokens}, "
            f"Total: {total_tokens}"
        )

    def get_conversation_summary(self) -> Dict[str, Any]:
        """
        Get summary of conversation state.

        Returns:
            Dictionary with conversation statistics and status
        """
        return {
            'conversation_id': self.conversation_id,
            'is_initialized': self.is_initialized,
            'turn_count': len(self.conversation_log),
            'has_proposal': self.current_proposal is not None,
            'ready_to_generate': self.is_ready_to_generate(),
            'column_count': len(self.current_proposal.get('columns', [])) if self.current_proposal else 0,
            'row_count': len(self.current_proposal.get('rows', {}).get('sample_rows', [])) if self.current_proposal else 0
        }
