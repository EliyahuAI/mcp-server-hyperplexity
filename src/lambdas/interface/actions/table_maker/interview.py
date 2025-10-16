"""
Quick Interview Handler for Table Maker.

This module handles the initial conversation phase where we quickly gather
context from the user about what table they want to build. It's designed to be
fast and lightweight, using a simpler model with no web search access.

The interview phase asks focused questions to understand:
1. What research table they want to build
2. What defines each row
3. What columns/information they're interested in
4. Who will use the table and for what purpose

Once it has enough context, it triggers preview generation.
"""

import logging
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

from ai_api_client import AIAPIClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class TableInterviewHandler:
    """
    Handles quick interactive interview to gather table requirements.

    This is Phase 1 of table generation - gathering context quickly.
    Phase 2 (preview generation) happens after trigger_preview is set to true.
    """

    def __init__(self, prompts_dir: str, schemas_dir: str):
        """
        Initialize interview handler.

        Args:
            prompts_dir: Path to prompts directory
            schemas_dir: Path to schemas directory
        """
        self.prompts_dir = prompts_dir
        self.schemas_dir = schemas_dir
        self.ai_client = AIAPIClient()

        # Load interview prompt and schema
        self.interview_prompt = self._load_prompt('interview.md')
        self.interview_schema = self._load_schema('interview_response.json')

        # Conversation history
        self.messages = []
        self.interview_context = {}

    def _load_prompt(self, filename: str) -> str:
        """Load prompt template from file."""
        try:
            path = os.path.join(self.prompts_dir, filename)
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load prompt {filename}: {e}")
            raise

    def _load_schema(self, filename: str) -> Dict[str, Any]:
        """Load JSON schema from file."""
        try:
            path = os.path.join(self.schemas_dir, filename)
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load schema {filename}: {e}")
            raise

    async def start_interview(
        self,
        user_message: str,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Start a new interview with the user's initial message.

        Args:
            user_message: User's initial request
            model: Model to use (defaults to fast Haiku model)
            max_tokens: Maximum tokens for response

        Returns:
            {
                'success': bool,
                'trigger_preview': bool,
                'follow_up_question': str,
                'context_web_research': list,
                'processing_steps': list,
                'table_name': str,
                'api_metadata': dict,
                'error': str or None
            }
        """
        try:
            logger.info(f"[INTERVIEW] Starting interview with message: '{user_message[:100]}...'")

            # Build prompt with user message
            prompt = self.interview_prompt.replace('{{USER_MESSAGE}}', user_message)

            # Add user message to history
            self.messages.append({
                'role': 'user',
                'content': user_message,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })

            # Call AI with structured output (NO web search for interview)
            logger.info(f"[INTERVIEW] Calling AI with model: {model} (web search disabled)")
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=self.interview_schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                max_web_searches=0,  # Explicitly disable web search for interview
                debug_name="table_maker_interview"
            )

            # Check for errors (same pattern as conversation_handler)
            if 'response' not in response and 'error' in response:
                error_msg = response.get('error', 'Unknown error during interview')
                logger.error(f"[INTERVIEW] AI call failed: {error_msg}")
                logger.error(f"[INTERVIEW] Full API response: {json.dumps(response, indent=2)}")
                return {
                    'success': False,
                    'trigger_preview': False,
                    'follow_up_question': '',
                    'context_web_research': [],
                    'processing_steps': [],
                    'table_name': '',
                    'api_metadata': {},
                    'error': error_msg
                }

            # Extract structured response (same pattern as conversation_handler)
            raw_response = response.get('response', {})

            # Parse the structured content from choices[0].message.content
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message']['content']
                structured_data = json.loads(content) if isinstance(content, str) else content
            elif 'ai_message' in raw_response:
                # Response is already structured (from cache)
                structured_data = raw_response
            else:
                logger.error(f"[INTERVIEW] Unexpected response structure: {json.dumps(raw_response, indent=2)[:500]}")
                structured_data = raw_response

            # Add AI response to history
            self.messages.append({
                'role': 'assistant',
                'content': json.dumps(structured_data, indent=2),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })

            # Store interview context
            self.interview_context = {
                'trigger_preview': structured_data.get('trigger_preview', False),
                'follow_up_question': structured_data.get('follow_up_question', ''),
                'context_web_research': structured_data.get('context_web_research', []),
                'processing_steps': structured_data.get('processing_steps', []),
                'table_name': structured_data.get('table_name', '')
            }

            logger.info(f"[INTERVIEW] Interview turn complete. Trigger preview: {self.interview_context['trigger_preview']}")

            # Return FULL API response for enhanced metrics aggregation
            # The response from call_structured_api contains everything needed
            return {
                'success': True,
                'trigger_preview': self.interview_context['trigger_preview'],
                'follow_up_question': self.interview_context['follow_up_question'],
                'context_web_research': self.interview_context['context_web_research'],
                'processing_steps': self.interview_context['processing_steps'],
                'table_name': self.interview_context['table_name'],
                'api_metadata': response,  # Full response from call_structured_api
                'error': None
            }

        except Exception as e:
            error_msg = f"Interview failed: {str(e)}"
            logger.error(f"[INTERVIEW] {error_msg}")
            import traceback
            logger.error(f"[INTERVIEW] Traceback: {traceback.format_exc()}")

            return {
                'success': False,
                'trigger_preview': False,
                'follow_up_question': '',
                'context_web_research': [],
                'processing_steps': [],
                'table_name': '',
                'api_metadata': {},
                'error': error_msg
            }

    async def continue_interview(
        self,
        user_message: str,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Continue the interview with a follow-up message.

        Args:
            user_message: User's follow-up response
            model: Model to use (defaults to fast Haiku model)
            max_tokens: Maximum tokens for response

        Returns:
            Same structure as start_interview
        """
        try:
            logger.info(f"[INTERVIEW] Continuing interview with message: '{user_message[:100]}...'")

            # Build conversation history for context
            conversation_text = "\n\n".join([
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                for msg in self.messages
            ])

            # Build prompt with full context
            prompt = self.interview_prompt.replace(
                '{{USER_MESSAGE}}',
                f"Previous conversation:\n{conversation_text}\n\nUser's latest message:\n{user_message}"
            )

            # Add user message to history
            self.messages.append({
                'role': 'user',
                'content': user_message,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })

            # Call AI with structured output (NO web search for interview)
            logger.info(f"[INTERVIEW] Calling AI with model: {model} (web search disabled)")
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=self.interview_schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                max_web_searches=0,  # Explicitly disable web search for interview
                debug_name="table_maker_interview_continue"
            )

            # Check for errors (same pattern as conversation_handler)
            if 'response' not in response and 'error' in response:
                error_msg = response.get('error', 'Unknown error during interview')
                logger.error(f"[INTERVIEW] AI call failed: {error_msg}")
                logger.error(f"[INTERVIEW] Full API response: {json.dumps(response, indent=2)}")
                return {
                    'success': False,
                    'trigger_preview': False,
                    'follow_up_question': '',
                    'context_web_research': [],
                    'processing_steps': [],
                    'table_name': '',
                    'api_metadata': {},
                    'error': error_msg
                }

            # Extract structured response (same pattern as conversation_handler)
            raw_response = response.get('response', {})

            # Parse the structured content from choices[0].message.content
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message']['content']
                structured_data = json.loads(content) if isinstance(content, str) else content
            elif 'ai_message' in raw_response:
                # Response is already structured (from cache)
                structured_data = raw_response
            else:
                logger.error(f"[INTERVIEW] Unexpected response structure: {json.dumps(raw_response, indent=2)[:500]}")
                structured_data = raw_response

            # Add AI response to history
            self.messages.append({
                'role': 'assistant',
                'content': json.dumps(structured_data, indent=2),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })

            # Update interview context
            self.interview_context = {
                'trigger_preview': structured_data.get('trigger_preview', False),
                'follow_up_question': structured_data.get('follow_up_question', ''),
                'context_web_research': structured_data.get('context_web_research', []),
                'processing_steps': structured_data.get('processing_steps', []),
                'table_name': structured_data.get('table_name', '')
            }

            logger.info(f"[INTERVIEW] Interview turn complete. Trigger preview: {self.interview_context['trigger_preview']}")

            # Return FULL API response for enhanced metrics aggregation
            # The response from call_structured_api contains everything needed
            return {
                'success': True,
                'trigger_preview': self.interview_context['trigger_preview'],
                'follow_up_question': self.interview_context['follow_up_question'],
                'context_web_research': self.interview_context['context_web_research'],
                'processing_steps': self.interview_context['processing_steps'],
                'table_name': self.interview_context['table_name'],
                'api_metadata': response,  # Full response from call_structured_api
                'error': None
            }

        except Exception as e:
            error_msg = f"Interview continuation failed: {str(e)}"
            logger.error(f"[INTERVIEW] {error_msg}")
            import traceback
            logger.error(f"[INTERVIEW] Traceback: {traceback.format_exc()}")

            return {
                'success': False,
                'trigger_preview': False,
                'follow_up_question': '',
                'context_web_research': [],
                'processing_steps': [],
                'table_name': '',
                'api_metadata': {},
                'error': error_msg
            }

    def get_interview_history(self) -> list:
        """Get the full interview conversation history."""
        return self.messages.copy()

    def get_interview_context(self) -> Dict[str, Any]:
        """Get the current interview context."""
        return self.interview_context.copy()
