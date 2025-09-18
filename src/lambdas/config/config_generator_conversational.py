#!/usr/bin/env python3
"""
Conversational Configuration System
Advanced interview system that handles sequential conversations, observations, and strategic changes
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import asyncio
import aiohttp
import time
import uuid
import yaml

# Import previous components
try:
    # Try relative imports first (for Lambda deployment)
    from .config_generator_step1 import PromptLoader, TableAnalyzer
    from .config_generator_step2_enhanced import EnhancedClaudeConfigGenerator, ConfigValidator
except ImportError:
    # Fallback to direct imports (for local development)
    from config_generator_step1 import PromptLoader, TableAnalyzer
    from config_generator_step2_enhanced import EnhancedClaudeConfigGenerator, ConfigValidator

# Import shared AI API client
try:
    from ai_api_client import AIAPIClient
except ImportError:
    # Fallback if running locally
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
    from ai_api_client import AIAPIClient

class ConversationalConfigSystem:
    """Advanced conversational system for config optimization"""
    
    def __init__(self, api_key=None):
        # Initialize shared AI API client
        self.ai_client = AIAPIClient()
        
        # Load settings from config file
        self._load_settings()
        
        self.temperature = 0.1
        
    def _load_settings(self):
        """Load configuration settings from JSON file"""
        import json
        import os
        
        settings_path = os.path.join(os.path.dirname(__file__), 'config_settings.json')
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            self.max_tokens = settings.get('max_tokens', 16000)
            self.model = settings.get('model', 'claude-opus-4-1')
        except (FileNotFoundError, json.JSONDecodeError):
            # Fallback to defaults if file not found
            self.max_tokens = 16000
            self.model = "claude-opus-4-1"
        
        # Load prompt templates
        self.prompt_loader = PromptLoader()
        self.conversation_prompt = self._load_conversation_prompt()
        
        # Conversation storage
        self.conversations = {}
        self.conversation_storage_dir = Path("conversations")
        self.conversation_storage_dir.mkdir(exist_ok=True)
    
    
    def _load_conversation_prompt(self):
        """Load conversation prompt template with variables"""
        prompt_path = Path("prompts/conversational_interview_prompt.md")
        if not prompt_path.exists():
            raise FileNotFoundError(f"Conversation prompt not found: {prompt_path}")
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _apply_prompt_variables(self, current_config, table_analysis, current_directive=None):
        """Apply variables to the prompt template"""
        domain_info = table_analysis.get('domain_info', {})
        
        # Set current directive - this is the main focus point
        if not current_directive:
            current_directive = "Focus on optimizing the configuration for data validation. Address any structural issues, model assignments, and validation requirements that need improvement."
        
        # Infer domain from table analysis
        domain_info = table_analysis.get('domain_info', {})
        inferred_domain = domain_info.get('inferred_domain', 'general')
        
        variables = {
            'current_directive': current_directive,
            'group_restructuring_strategy': 'Analyze current groups and create smaller, more focused groups based on actual data source patterns and search efficiency',
            'notes_clarification_strategy': 'Remove technical implementation details from general notes, focus on business guidance and validation priorities',
            'model_optimization_strategy': 'Use sonar-pro as default for most fields. Use claude-sonnet-4-0 sparingly only for complex analysis requiring domain expertise. High context only when nuanced interpretation is essential.',
            'column_improvement_strategy': 'Refine column notes for clarity, update examples to be more representative, ensure format specifications are precise',
            'domain_industry': inferred_domain.title() if inferred_domain != 'general' else 'Data validation',
            'domain_focus': domain_info.get('inferred_purpose', 'General data validation and quality assurance'),
            'domain_specific_concerns': 'Data quality, validation accuracy, efficient processing',
            'business_priorities': 'Data accuracy, processing efficiency, validation reliability'
        }
        
        prompt = self.conversation_prompt
        for var, value in variables.items():
            prompt = prompt.replace(f"{{{{{var}}}}}", value)
        
        return prompt
    
    async def start_conversation(self, config_path, table_analysis, initial_message=None):
        """Start a new conversation session"""
        conversation_id = f"conv_{uuid.uuid4().hex[:8]}"
        
        # Load current configuration
        with open(config_path, 'r', encoding='utf-8') as f:
            current_config = json.load(f)
        
        # Generate versioned config filename based on Excel file
        excel_filename = table_analysis['basic_info']['filename']
        base_name = Path(excel_filename).stem
        
        # Find next version number
        version_num = 1
        while True:
            version_filename = f"{base_name}_config_V{version_num:02d}.json"
            if not Path(version_filename).exists():
                break
            version_num += 1
        
        # Initialize conversation
        conversation = {
            'conversation_id': conversation_id,
            'created_at': datetime.now().isoformat(),
            'config_path': str(config_path),
            'versioned_config_path': version_filename,
            'table_analysis': table_analysis,
            'current_config': current_config,
            'messages': [],
            'changes_made': []
        }
        
        # Add initial message if provided
        if initial_message:
            conversation['messages'].append({
                'timestamp': datetime.now().isoformat(),
                'role': 'user',
                'content': initial_message
            })
        
        # Save conversation
        self.conversations[conversation_id] = conversation
        self._save_conversation(conversation)
        
        return conversation_id
    
    async def continue_conversation(self, conversation_id, user_message):
        """Continue an existing conversation"""
        conversation = self._load_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        # Add user message
        conversation['messages'].append({
            'timestamp': datetime.now().isoformat(),
            'role': 'user',
            'content': user_message
        })
        
        # Generate AI response
        response = await self._generate_ai_response(conversation)
        
        # Add AI response
        conversation['messages'].append({
            'timestamp': datetime.now().isoformat(),
            'role': 'assistant',
            'content': response['conversation_response'],
            'actions_taken': response.get('actions_taken', []),
            'reasoning': response.get('reasoning', ''),
            'next_suggestions': response.get('next_suggestions', [])
        })
        
        # Always check current config for issues (even if no changes)
        current_config = conversation['current_config']
        
        # Validate column names match the Excel file
        validated_config = self._validate_and_fix_column_names(
            current_config,
            conversation['table_analysis']
        )
        
        # Validate config structure
        validation_result = self._validate_config_structure(validated_config)
        
        # If there are validation issues, add them to the response
        if not validation_result['valid'] or validation_result['warnings']:
            response['validation_result'] = validation_result
            if not validation_result['valid']:
                response['validation_errors'] = validation_result['errors']
            if validation_result['warnings']:
                response['validation_warnings'] = validation_result['warnings']
        
        # Apply any configuration changes directly
        if response.get('config_changes'):
            updated_config = self._apply_config_changes(
                validated_config,
                response['config_changes']
            )
            
            conversation['current_config'] = updated_config
            
            # Increment version and update metadata
            current_version = updated_config.get('generation_metadata', {}).get('version', 1)
            new_version = current_version + 1
            
            if 'generation_metadata' not in updated_config:
                updated_config['generation_metadata'] = {}
            updated_config['generation_metadata']['version'] = new_version
            updated_config['generation_metadata']['last_updated'] = datetime.now().isoformat()
            
            # Reorder config structure before saving
            updated_config = self._reorder_config_structure(updated_config)
            
            # Save updated config immediately
            versioned_path = conversation['versioned_config_path']
            with open(versioned_path, 'w', encoding='utf-8') as f:
                json.dump(updated_config, f, indent=2, default=str)
            
            # Track changes
            conversation['changes_made'].append({
                'timestamp': datetime.now().isoformat(),
                'user_message': user_message,
                'actions_taken': response.get('actions_taken', []),
                'config_changes': response.get('config_changes', []),
                'version': new_version,
                'saved_to': versioned_path,
                'validation_result': validation_result
            })
        elif validated_config != current_config:
            # Column fixes were made, save the updated config
            conversation['current_config'] = validated_config
            
            # Increment version for column fixes
            current_version = validated_config.get('generation_metadata', {}).get('version', 1)
            new_version = current_version + 1
            
            if 'generation_metadata' not in validated_config:
                validated_config['generation_metadata'] = {}
            validated_config['generation_metadata']['version'] = new_version
            validated_config['generation_metadata']['last_updated'] = datetime.now().isoformat()
            
            # Reorder config structure before saving
            validated_config = self._reorder_config_structure(validated_config)
            
            # Save updated config
            versioned_path = conversation['versioned_config_path']
            with open(versioned_path, 'w', encoding='utf-8') as f:
                json.dump(validated_config, f, indent=2, default=str)
            
            # Track column fixes
            conversation['changes_made'].append({
                'timestamp': datetime.now().isoformat(),
                'user_message': user_message,
                'actions_taken': ['Fixed column name mismatches'],
                'config_changes': [],
                'version': new_version,
                'saved_to': versioned_path,
                'validation_result': validation_result
            })
        
        # Save updated conversation
        self._save_conversation(conversation)
        
        return response
    
    async def _generate_ai_response(self, conversation):
        """Generate AI response using Claude via shared AI API client"""
        # Build conversation context
        context = self._build_conversation_context(conversation)
        
        # Apply prompt variables with current directive
        current_directive = "CRITICAL: Address the user's current request with specific, actionable changes. Focus on implementing the requested modifications to the configuration immediately."
        
        system_prompt = self._apply_prompt_variables(
            conversation['current_config'],
            conversation['table_analysis'],
            current_directive
        )
        
        # Define tool schema
        tool_schema = self._get_conversation_tool_schema()
        
        # Use shared AI API client
        prompt = f"{system_prompt}\n\nConversation Context:\n{context}"
        
        try:
            response = await self.ai_client.call_structured_api(
                prompt=prompt,
                schema=tool_schema,
                model=self.model,
                tool_name="optimize_config",
                max_web_searches=0,
                debug_name="config_conversational_optimization"
            )
            
            return response
            
        except Exception as e:
            logger.error(f"AI API call failed: {e}")
            raise
    
    def _build_conversation_context(self, conversation):
        """Build conversation context for AI"""
        config_name = Path(conversation['versioned_config_path']).stem
        current_version = conversation['current_config'].get('generation_metadata', {}).get('version', 1)
        
        context = f"""
[Config File: {config_name}]

CURRENT CONFIGURATION ANALYSIS:
{self._analyze_current_config(conversation['current_config'])}

CONVERSATION HISTORY:
"""
        
        # Add recent messages (last 10 to avoid context overflow)
        recent_messages = conversation['messages'][-10:]
        for msg in recent_messages:
            role = msg['role'].upper()
            content = msg['content']
            timestamp = msg['timestamp']
            
            context += f"\n[{timestamp}] {role}: {content}"
            
            if msg['role'] == 'assistant' and msg.get('actions_taken'):
                context += f"\n    ACTIONS TAKEN: {msg['actions_taken']}"
        
        # Add latest user message
        if conversation['messages']:
            latest_message = conversation['messages'][-1]
            if latest_message['role'] == 'user':
                context += f"\n\nLATEST USER MESSAGE: {latest_message['content']}"
        
        return context
    
    def _analyze_current_config(self, config):
        """Analyze current configuration for context"""
        targets = config.get('validation_targets', [])
        groups = config.get('search_groups', [])
        
        # Analyze importance distribution
        importance_counts = {}
        model_usage = {}
        context_usage = {}
        
        for target in targets:
            importance = target.get('importance', 'UNKNOWN')
            importance_counts[importance] = importance_counts.get(importance, 0) + 1
            
            model = target.get('preferred_model', 'default')
            model_usage[model] = model_usage.get(model, 0) + 1
            
            context = target.get('search_context_size', 'default')
            context_usage[context] = context_usage.get(context, 0) + 1
        
        analysis = f"""
Configuration Summary:
- Validation Targets: {len(targets)}
- Search Groups: {len(groups)}
- Importance Distribution: {importance_counts}
- Model Usage: {model_usage}
- Context Usage: {context_usage}

Current Search Groups:
"""
        
        for group in groups:
            analysis += f"- Group {group['group_id']}: {group['group_name']} ({group.get('model', 'default')} model, {group.get('search_context', 'default')} context)\n"
        
        return analysis
    
    def _get_conversation_tool_schema(self):
        """Get schema for conversation response tool"""
        return {
            "type": "object",
            "properties": {
                "conversation_response": {
                    "type": "string",
                    "description": "Natural language response to the user"
                },
                "actions_taken": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of specific actions taken (if any)"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of why changes were made"
                },
                "next_suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Suggested next steps or improvements"
                },
                "config_changes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["importance", "model", "context", "group", "notes", "examples", "format"]},
                            "column": {"type": "string"},
                            "old_value": {"type": "string"},
                            "new_value": {"type": "string"},
                            "reason": {"type": "string"}
                        },
                        "required": ["type", "reason"]
                    },
                    "description": "Specific configuration changes made"
                }
            },
            "required": ["conversation_response"]
        }
    
    def _extract_response_from_tool(self, response):
        """Extract response from Claude's tool response"""
        try:
            for content_item in response.get('content', []):
                if content_item.get('type') == 'tool_use' and content_item.get('name') == 'config_conversation_response':
                    return content_item.get('input', {})
            raise ValueError("Could not extract response from tool")
        except Exception as e:
            print(f"Error extracting response: {e}")
            raise
    
    def _apply_config_changes(self, config, changes):
        """Apply configuration changes"""
        updated_config = config.copy()
        
        for change in changes:
            change_type = change.get('type')
            column = change.get('column')
            new_value = change.get('new_value')
            
            if change_type == 'importance' and column:
                # Update importance level
                for target in updated_config.get('validation_targets', []):
                    if target['column'] == column:
                        target['importance'] = new_value
                        break
            
            elif change_type == 'model' and column:
                # Update preferred model
                for target in updated_config.get('validation_targets', []):
                    if target['column'] == column:
                        target['preferred_model'] = new_value
                        break
            
            elif change_type == 'context' and column:
                # Update search context
                for target in updated_config.get('validation_targets', []):
                    if target['column'] == column:
                        target['search_context_size'] = new_value
                        break
            
            elif change_type == 'notes' and column:
                # Update notes
                for target in updated_config.get('validation_targets', []):
                    if target['column'] == column:
                        target['notes'] = new_value
                        break
            
            elif change_type == 'group':
                # Handle group restructuring
                if 'search_groups' in updated_config:
                    # This would need more sophisticated logic
                    pass
        
        return updated_config
    
    def _validate_and_fix_column_names(self, config, table_analysis):
        """Validate and fix column names to match Excel file"""
        excel_columns = set(table_analysis['basic_info']['column_names'])
        config_columns = set()
        
        # Track changes made
        column_fixes = []
        
        for target in config.get('validation_targets', []):
            column_name = target.get('column')
            if column_name:
                config_columns.add(column_name)
                
                # Check if column exists in Excel
                if column_name not in excel_columns:
                    # Try to find close match
                    close_match = self._find_close_column_match(column_name, excel_columns)
                    if close_match:
                        column_fixes.append({
                            'original': column_name,
                            'fixed': close_match,
                            'reason': 'Column name mismatch - auto-corrected'
                        })
                        target['column'] = close_match
                        print(f"Fixed column name: '{column_name}' → '{close_match}'")
                    else:
                        print(f"WARNING: Column '{column_name}' not found in Excel file")
        
        # Check for Excel columns not in config
        missing_columns = excel_columns - config_columns
        if missing_columns:
            print(f"WARNING: Excel columns not in config: {missing_columns}")
            
            # AUTO-FIX: Add missing columns with default settings
            print(f"AUTO-FIXING: Adding {len(missing_columns)} missing columns to config")
            for missing_col in missing_columns:
                # Add validation target for missing column with default settings
                default_target = {
                    "column": missing_col,
                    "description": f"Auto-generated entry for missing column: {missing_col}",
                    "importance": "MEDIUM",
                    "format": "String",
                    "notes": "Auto-added due to missing validation target",
                    "examples": ["[sample data not available]"],
                    "search_group": 1  # Default to first search group
                }
                
                if 'validation_targets' not in config:
                    config['validation_targets'] = []
                
                config['validation_targets'].append(default_target)
                print(f"  Added validation target for: {missing_col}")
        
        # Add column fixes to metadata
        if column_fixes or missing_columns:
            if 'generation_metadata' not in config:
                config['generation_metadata'] = {}
            config['generation_metadata']['column_fixes'] = column_fixes
            if missing_columns:
                config['generation_metadata']['auto_added_columns'] = list(missing_columns)
        
        return config
    
    def _find_close_column_match(self, column_name, excel_columns):
        """Find closest matching column name"""
        import difflib
        
        # Try exact match first (case insensitive)
        for excel_col in excel_columns:
            if column_name.lower() == excel_col.lower():
                return excel_col
        
        # Try close matches
        close_matches = difflib.get_close_matches(column_name, excel_columns, n=1, cutoff=0.8)
        return close_matches[0] if close_matches else None
    
    def _validate_config_structure(self, config):
        """Validate configuration structure using the API validation logic"""
        try:
            # Import the validation function
            sys.path.append('src/interface_lambda/actions')
            from config_validation import validate_config_structure
            
            is_valid, errors, warnings = validate_config_structure(config)
            
            validation_result = {
                'valid': is_valid,
                'errors': errors,
                'warnings': warnings
            }
            
            if not is_valid:
                print(f"CONFIG VALIDATION FAILED:")
                for error in errors:
                    print(f"  ERROR: {error}")
            
            if warnings:
                print(f"CONFIG VALIDATION WARNINGS:")
                for warning in warnings:
                    print(f"  WARNING: {warning}")
            
            if is_valid:
                print("SUCCESS: Configuration validation passed!")
                if warnings:
                    print(f"   ({len(warnings)} warnings)")
            
            return validation_result
            
        except ImportError as e:
            print(f"WARNING: Could not import validation function: {e}")
            return {
                'valid': True,
                'errors': [],
                'warnings': ['Validation function not available - skipped validation']
            }
    
    def _reorder_config_structure(self, config):
        """Reorder config structure: general settings first, then search groups, validation targets, metadata last"""
        ordered_config = {}
        
        # 1. General settings first
        if 'general_notes' in config:
            ordered_config['general_notes'] = config['general_notes']
        
        if 'default_model' in config:
            ordered_config['default_model'] = config['default_model']
        
        if 'default_search_context_size' in config:
            ordered_config['default_search_context_size'] = config['default_search_context_size']
        
        # 2. Search groups
        if 'search_groups' in config:
            ordered_config['search_groups'] = config['search_groups']
        
        # 3. Validation targets (remove group settings if they're part of search groups)
        if 'validation_targets' in config:
            ordered_config['validation_targets'] = self._remove_redundant_group_settings(
                config['validation_targets'], 
                config.get('search_groups', [])
            )
        
        # 4. Other existing information (preserve any other fields)
        for key, value in config.items():
            if key not in ['general_notes', 'default_model', 'default_search_context_size', 
                          'search_groups', 'validation_targets', 'generation_metadata', 'config_change_log']:
                ordered_config[key] = value
        
        # 5. Generation metadata and config log at the end
        if 'generation_metadata' in config:
            ordered_config['generation_metadata'] = config['generation_metadata']
        
        if 'config_change_log' in config:
            ordered_config['config_change_log'] = config['config_change_log']
        
        return ordered_config
    
    def _remove_redundant_group_settings(self, validation_targets, search_groups):
        """Remove group settings from validation targets if they are parts of a search group"""
        if not search_groups:
            return validation_targets
        
        # Create a mapping of group_id to group settings
        group_settings = {}
        for group in search_groups:
            group_id = group.get('group_id')
            if group_id is not None:
                group_settings[group_id] = {
                    'model': group.get('model'),
                    'search_context': group.get('search_context')
                }
        
        # Process validation targets
        updated_targets = []
        for target in validation_targets:
            updated_target = target.copy()
            search_group_id = target.get('search_group')
            
            # If target belongs to a search group, remove redundant settings
            if search_group_id in group_settings:
                group_model = group_settings[search_group_id].get('model')
                group_context = group_settings[search_group_id].get('search_context')
                
                # Remove preferred_model if it matches the group model
                if (updated_target.get('preferred_model') == group_model and 
                    group_model is not None):
                    updated_target.pop('preferred_model', None)
                
                # Remove search_context_size if it matches the group context
                if (updated_target.get('search_context_size') == group_context and 
                    group_context is not None):
                    updated_target.pop('search_context_size', None)
            
            updated_targets.append(updated_target)
        
        return updated_targets
    
    def _save_conversation(self, conversation):
        """Save conversation to storage"""
        conversation_id = conversation['conversation_id']
        conversation_file = self.conversation_storage_dir / f"{conversation_id}.json"
        
        with open(conversation_file, 'w', encoding='utf-8') as f:
            json.dump(conversation, f, indent=2, default=str)
        
        # Also store in memory
        self.conversations[conversation_id] = conversation
    
    def _load_conversation(self, conversation_id):
        """Load conversation from storage"""
        # Try memory first
        if conversation_id in self.conversations:
            return self.conversations[conversation_id]
        
        # Try file storage
        conversation_file = self.conversation_storage_dir / f"{conversation_id}.json"
        if conversation_file.exists():
            with open(conversation_file, 'r', encoding='utf-8') as f:
                conversation = json.load(f)
                self.conversations[conversation_id] = conversation
                return conversation
        
        return None
    
    def save_updated_config(self, conversation_id, output_path):
        """Save the updated configuration from conversation"""
        conversation = self._load_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        # Add conversation metadata to config
        updated_config = conversation['current_config'].copy()
        
        # Add conversation history to change log
        if 'config_change_log' not in updated_config:
            updated_config['config_change_log'] = []
        
        # Add conversation entry
        conversation_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': 'conversational_optimization',
            'conversation_id': conversation_id,
            'message_count': len(conversation['messages']),
            'changes_made': conversation['changes_made']
        }
        
        updated_config['config_change_log'].append(conversation_entry)
        
        # Save to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(updated_config, f, indent=2, default=str)
        
        return updated_config

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Conversational Configuration System',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--config', 
                       help='Path to current configuration file (required for new conversations)')
    
    parser.add_argument('--excel', 
                       help='Path to Excel file for table analysis')
    
    parser.add_argument('--conversation-id',
                       help='Existing conversation ID to continue')
    
    parser.add_argument('--message', 
                       help='Message to send in conversation')
    
    parser.add_argument('--output', 
                       help='Output file for updated configuration')
    
    parser.add_argument('--api-key',
                       help='Claude API key')
    
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Verbose output')
    
    return parser.parse_args()

async def main():
    """Main function"""
    args = parse_arguments()
    
    print("CONVERSATIONAL CONFIGURATION SYSTEM")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Initialize system
        system = ConversationalConfigSystem(api_key=args.api_key)
        
        # Load table analysis if needed
        table_analysis = None
        if args.excel:
            print(f"\\nAnalyzing table: {args.excel}")
            analyzer = TableAnalyzer()
            table_analysis = analyzer.analyze_table(args.excel)
        
        if args.conversation_id:
            # Continue existing conversation
            if not args.message:
                print("ERROR: --message required to continue conversation")
                return 1
            
            print(f"\\nContinuing conversation: {args.conversation_id}")
            print(f"User message: {args.message}")
            
            response = await system.continue_conversation(args.conversation_id, args.message)
            
            print(f"\\nAI Response: {response['conversation_response']}")
            
            if response.get('actions_taken'):
                print(f"\\nActions Taken:")
                for action in response['actions_taken']:
                    print(f"  - {action}")
            
            # Show actual config changes made
            if response.get('config_changes'):
                print(f"\\nConfig Changes Made:")
                for change in response['config_changes']:
                    print(f"  - {change.get('type', 'unknown')}: {change.get('column', 'general')} = {change.get('new_value', 'updated')}")
            
            # Show validation results
            if response.get('validation_errors'):
                print(f"\\nValidation Errors Found:")
                for error in response['validation_errors']:
                    print(f"  ERROR: {error}")
            
            if response.get('validation_warnings'):
                print(f"\\nValidation Warnings:")
                for warning in response['validation_warnings']:
                    print(f"  WARNING: {warning}")
            
            if response.get('reasoning'):
                print(f"\\nReasoning: {response['reasoning']}")
            
            if response.get('next_suggestions'):
                print(f"\\nNext Suggestions:")
                for suggestion in response['next_suggestions']:
                    print(f"  - {suggestion}")
            
            # Show version and file information
            conversation = system._load_conversation(args.conversation_id)
            if conversation and conversation.get('changes_made'):
                latest_change = conversation['changes_made'][-1]
                print(f"\\nConfig updated to version {latest_change.get('version', '?')} saved to: {latest_change.get('saved_to', '?')}")
            
            # Save updated config if requested
            if args.output:
                system.save_updated_config(args.conversation_id, args.output)
                print(f"\\nAdditional copy saved: {args.output}")
        
        else:
            # Start new conversation
            if not args.config:
                print("ERROR: --config required to start new conversation")
                return 1
            if not table_analysis:
                print("ERROR: --excel required to start new conversation")
                return 1
            
            conversation_id = await system.start_conversation(
                args.config,
                table_analysis,
                args.message
            )
            
            print(f"\\nStarted new conversation: {conversation_id}")
            
            if args.message:
                response = await system.continue_conversation(conversation_id, args.message)
                
                print(f"\\nAI Response: {response['conversation_response']}")
                
                if response.get('actions_taken'):
                    print(f"\\nActions Taken:")
                    for action in response['actions_taken']:
                        print(f"  - {action}")
                
                # Save updated config if requested
                if args.output:
                    system.save_updated_config(conversation_id, args.output)
                    print(f"\\nUpdated config saved: {args.output}")
        
        print("\\nSUCCESS: Conversational system completed!")
        
    except Exception as e:
        print(f"\\nERROR: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))