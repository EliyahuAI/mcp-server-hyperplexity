"""
Upload Interview Handler for Table Uploads.

This module handles the initial conversation phase after a user uploads an Excel file.
Instead of immediately generating a config, we engage in a quick interview to:
1. Understand the table structure and purpose
2. Identify ID columns and research columns
3. Clarify any ambiguities
4. Get user approval before generating config

The interview phase is designed to be fast and lightweight, using a simpler model
with no web search access.
"""

import logging
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

from shared.ai_api_client import ai_client

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Load config file
def _load_config() -> Dict[str, Any]:
    """Load upload interview config from JSON file."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'upload_interview_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[UPLOAD_INTERVIEW] Failed to load config from {config_path}: {e}, using defaults")
        return {}

# Load config at module level
_CONFIG = _load_config()

def get_interview_model() -> list:
    """Get the model(s) to use for interview from config. Returns list of models."""
    interview_cfg = _CONFIG.get('interview', {})
    model = interview_cfg.get('model', ['openrouter/gemini-3-flash-preview-low', 'gemini-3-flash-preview-low', 'moonshotai/kimi-k2.5'])
    # Apply model_role override from ModelConfig CSV if available
    model_role = interview_cfg.get('model_role')
    if model_role:
        try:
            from model_config_loader import ModelConfig
            resolved = ModelConfig.get_with_fallbacks(model_role)
            if resolved:
                model = resolved
        except Exception as e:
            logger.warning(f"ModelConfig override skipped for interview: {e}")
    # Ensure it's always a list
    if isinstance(model, str):
        model = [model]
    return model

def get_interview_max_tokens() -> int:
    """Get max tokens for interview from config."""
    return _CONFIG.get('interview', {}).get('max_tokens', 4000)


class UploadInterviewHandler:
    """
    Handles quick interactive interview to gather validation requirements for uploaded table.

    This is Phase 1 of config generation - gathering context and approval.
    Phase 2 (config generation) happens after trigger_config_generation is set to true.
    """

    def __init__(self, prompts_dir: str, schemas_dir: str):
        """
        Initialize upload interview handler.

        Args:
            prompts_dir: Path to prompts directory
            schemas_dir: Path to schemas directory
        """
        self.prompts_dir = prompts_dir
        self.schemas_dir = schemas_dir
        self.ai_client = ai_client  # Use module-level singleton

        # Load interview prompt and schema
        self.interview_prompt = self._load_prompt('upload_interview.md')
        self.interview_schema = self._load_schema('upload_interview_response.json')

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
        table_analysis: Dict[str, Any],
        user_message: str = "",
        model: str = None,
        max_tokens: int = None,
        skip_interview: bool = False,
    ) -> Dict[str, Any]:
        """
        Start a new interview with table analysis.

        Args:
            table_analysis: Dictionary containing table structure info (columns, sample rows, etc.)
            user_message: Optional initial user message (empty for first interaction)
            model: Model to use (defaults to fast Gemini model)
            max_tokens: Maximum tokens for response

        Returns:
            {
                'success': bool,
                'mode': int,
                'trigger_config_generation': bool,
                'ai_message': str,
                'inferred_context': dict,
                'confirmation_response': dict or None,
                'config_instructions': str or None,
                'api_metadata': dict,
                'error': str or None
            }
        """
        try:
            # Use config defaults if not provided
            if model is None:
                model = get_interview_model()  # Returns list
            elif isinstance(model, str):
                model = [model]  # Ensure it's a list
            if max_tokens is None:
                max_tokens = get_interview_max_tokens()

            logger.info(f"[UPLOAD_INTERVIEW] Starting interview for table upload")
            logger.info(f"[UPLOAD_INTERVIEW] User message: '{user_message[:100]}...'")

            # Format table analysis for prompt
            table_analysis_str = self._format_table_analysis(table_analysis)

            # Build conversation history string
            conversation_history = self._format_conversation_history()

            # Build prompt with variables and current date
            today_date = datetime.utcnow().strftime('%B %d, %Y')
            prompt = self.interview_prompt.replace('{{TODAY_DATE}}', today_date)
            prompt = prompt.replace('{{TABLE_ANALYSIS}}', table_analysis_str)
            prompt = prompt.replace('{{CONVERSATION_HISTORY}}', conversation_history)
            prompt = prompt.replace('{{USER_MESSAGE}}', user_message if user_message else "(No message - this is the initial analysis)")
            if skip_interview:
                directive = (
                    "## ⚡ INSTRUCTIONS MODE — Skip Interview\n\n"
                    "The user has provided explicit instructions via the API. "
                    "Do NOT ask questions (skip Mode 1). "
                    "Do NOT show a structure for confirmation (skip Mode 2).\n\n"
                    "**Output Mode 3 directly** (`trigger_config_generation: true`) using your best "
                    "interpretation of the table structure and the user's instructions above. "
                    "Fill `inferred_context` and `config_instructions` with your best inferences — "
                    "this is an automated API session with no human present to answer follow-up questions.\n\n"
                )
                prompt = prompt.replace('{{INSTRUCTIONS_MODE_DIRECTIVE}}', directive)
            else:
                prompt = prompt.replace('{{INSTRUCTIONS_MODE_DIRECTIVE}}', '')

            # Add user message to history if provided
            if user_message:
                self.messages.append({
                    'role': 'user',
                    'content': user_message,
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                })

            # Call AI with structured output (NO web search for interview)
            logger.info(f"[UPLOAD_INTERVIEW] Calling AI with model chain: {model} (web search disabled)")
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=self.interview_schema,
                model=model,
                max_tokens=max_tokens,
                use_cache=True,
                max_web_searches=0,  # Explicitly disable web search for interview
                debug_name="upload_interview"
            )

            # Check for errors
            if 'response' not in response and 'error' in response:
                error_msg = response.get('error', 'Unknown error during upload interview')
                logger.error(f"[UPLOAD_INTERVIEW] AI call failed: {error_msg}")
                logger.error(f"[UPLOAD_INTERVIEW] Full API response: {json.dumps(response, indent=2)}")
                return {
                    'success': False,
                    'mode': 1,
                    'trigger_config_generation': False,
                    'ai_message': '',
                    'inferred_context': {},
                    'confirmation_response': None,
                    'config_instructions': None,
                    'api_metadata': {},
                    'error': error_msg
                }

            # Extract structured response
            raw_response = response.get('response', {})

            # Parse the structured content from choices[0].message.content
            if 'choices' in raw_response and len(raw_response['choices']) > 0:
                content = raw_response['choices'][0]['message'].get('content', [])

                # Handle both string (normalized format) and list (raw format) content
                structured_content = None
                if isinstance(content, str):
                    # Normalized format: content is a JSON string
                    try:
                        structured_content = json.loads(content)
                    except json.JSONDecodeError:
                        logger.error(f"[UPLOAD_INTERVIEW] Failed to parse string content as JSON")
                elif isinstance(content, list):
                    # Raw format: content is a list of content blocks
                    for block in content:
                        if isinstance(block, dict) and block.get('type') == 'text':
                            try:
                                structured_content = json.loads(block.get('text', '{}'))
                                break
                            except json.JSONDecodeError:
                                continue

                if not structured_content:
                    logger.error(f"[UPLOAD_INTERVIEW] No structured content found in response")
                    return {
                        'success': False,
                        'mode': 1,
                        'trigger_config_generation': False,
                        'ai_message': '',
                        'inferred_context': {},
                        'confirmation_response': None,
                        'config_instructions': None,
                        'api_metadata': {},
                        'error': 'No structured content in AI response'
                    }

                # Extract fields
                mode = structured_content.get('mode', 1)
                trigger_config_generation = structured_content.get('trigger_config_generation', False)
                ai_message = structured_content.get('ai_message', '')
                inferred_context = structured_content.get('inferred_context', {})
                confirmation_response = structured_content.get('confirmation_response')
                config_instructions = structured_content.get('config_instructions')

                # Add assistant response to history
                self.messages.append({
                    'role': 'assistant',
                    'content': structured_content,
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                })

                # Store context for next turn
                if inferred_context:
                    self.interview_context.update(inferred_context)

                # Extract API metadata
                api_metadata = {
                    'model': raw_response.get('model', model),
                    'usage': raw_response.get('usage', {}),
                }

                logger.info(f"[UPLOAD_INTERVIEW] Interview completed - Mode: {mode}, Trigger: {trigger_config_generation}")

                return {
                    'success': True,
                    'mode': mode,
                    'trigger_config_generation': trigger_config_generation,
                    'ai_message': ai_message,
                    'inferred_context': inferred_context,
                    'confirmation_response': confirmation_response,
                    'config_instructions': config_instructions,
                    'api_metadata': api_metadata,
                    'error': None
                }
            else:
                logger.error(f"[UPLOAD_INTERVIEW] Unexpected response format: {json.dumps(raw_response, indent=2)}")
                return {
                    'success': False,
                    'mode': 1,
                    'trigger_config_generation': False,
                    'ai_message': '',
                    'inferred_context': {},
                    'confirmation_response': None,
                    'config_instructions': None,
                    'api_metadata': {},
                    'error': 'Unexpected response format from AI'
                }

        except Exception as e:
            logger.error(f"[UPLOAD_INTERVIEW] Error in interview: {str(e)}")
            import traceback
            logger.error(f"[UPLOAD_INTERVIEW] Traceback: {traceback.format_exc()}")
            return {
                'success': False,
                'mode': 1,
                'trigger_config_generation': False,
                'ai_message': '',
                'inferred_context': {},
                'confirmation_response': None,
                'config_instructions': None,
                'api_metadata': {},
                'error': str(e)
            }

    async def continue_interview(
        self,
        user_message: str,
        model: str = None,
        max_tokens: int = None
    ) -> Dict[str, Any]:
        """
        Continue an existing interview with user's response.

        Args:
            user_message: User's response to previous question or approval
            model: Model to use
            max_tokens: Maximum tokens for response

        Returns:
            Same format as start_interview()
        """
        # Use empty table analysis for continuation (already have it from start)
        return await self.start_interview(
            table_analysis={},  # Not needed for continuation
            user_message=user_message,
            model=model,
            max_tokens=max_tokens
        )

    def _format_table_analysis(self, table_analysis: Dict[str, Any]) -> str:
        """Format table analysis for prompt."""
        if not table_analysis:
            return "(Table analysis from previous turn)"

        parts = []

        # Columns
        columns = table_analysis.get('columns', [])
        if columns:
            parts.append(f"**Columns ({len(columns)}):**")
            for col in columns[:20]:  # Limit to first 20 columns
                parts.append(f"- {col}")
            if len(columns) > 20:
                parts.append(f"- ... and {len(columns) - 20} more columns")

        # Row count
        row_count = table_analysis.get('row_count', 0)
        parts.append(f"\n**Row count:** {row_count}")

        # Sample rows
        sample_rows = table_analysis.get('sample_rows', [])
        if sample_rows:
            parts.append(f"\n**Sample rows (first {len(sample_rows)}):**")
            for i, row in enumerate(sample_rows[:3], 1):
                parts.append(f"\nRow {i}:")
                for col, value in row.items():
                    # Skip internal metadata fields (e.g., _row_key, _history)
                    if col.startswith('_'):
                        continue
                    # Truncate long values
                    value_str = str(value)[:100]
                    if len(str(value)) > 100:
                        value_str += "..."
                    parts.append(f"  - {col}: {value_str}")

        return '\n'.join(parts)

    def _format_conversation_history(self) -> str:
        """Format conversation history for prompt."""
        if not self.messages:
            return "(No previous conversation)"

        history_parts = []
        for msg in self.messages:
            role = msg['role'].upper()
            content = msg['content']

            # Format content based on type
            if isinstance(content, dict):
                content_str = json.dumps(content, indent=2)
            else:
                content_str = str(content)

            history_parts.append(f"**{role}:** {content_str}")

        return '\n\n'.join(history_parts)
