#!/usr/bin/env python3
"""
Config Generator - Step 2 Enhanced: Claude 4 with Multiple Prompt Strategies
Testing different prompt approaches to improve config generation quality

This enhanced version:
1. Uses Claude 4 (claude-sonnet-4-0)
2. Tests multiple prompt strategies
3. Provides better domain-specific guidance
4. Includes iterative improvement capabilities
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import asyncio
import time

# Import Step 1 components
from config_generator_step1 import PromptLoader, TableAnalyzer

# Import shared AI API client
try:
    from ai_api_client import AIAPIClient
except ImportError:
    # Fallback if running locally
    import sys
    import os
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
    from ai_api_client import AIAPIClient

# Default paths
DEFAULT_EXCEL = r"tables\RatioCompetitiveIntelligence\RatioCompetitiveIntelligence_Verified1.xlsx"
DEFAULT_CONFIG = r"tables\RatioCompetitiveIntelligence\column_config_simplified.json"

class EnhancedClaudeConfigGenerator:
    """Enhanced config generator with multiple prompt strategies"""
    
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
        
        # Available prompt strategies
        self.prompt_strategies = {
            'standard': self._build_standard_prompt,
            'domain_expert': self._build_domain_expert_prompt,
            'iterative': self._build_iterative_prompt,
            'competitive_intelligence': self._build_competitive_intel_prompt
        }
        
    async def generate_config_with_strategy(self, table_analysis, instruction_prompt, strategy='competitive_intelligence', existing_config=None):
        """Generate configuration using specified strategy"""
        
        if strategy not in self.prompt_strategies:
            raise ValueError(f"Unknown strategy: {strategy}. Available: {list(self.prompt_strategies.keys())}")
            
        print(f"Using prompt strategy: {strategy}")
        
        # Build the prompt using selected strategy
        prompt_builder = self.prompt_strategies[strategy]
        prompt = prompt_builder(table_analysis, instruction_prompt, existing_config)
        
        # Make API call
        config = await self._call_claude_api(prompt, table_analysis, strategy, instruction_prompt, existing_config)
        
        return config
    
    async def _call_claude_api(self, prompt, table_analysis, strategy, instruction_prompt=None, existing_config=None):
        """Make the actual API call to Claude using shared AI API client"""
        
        # Enhanced system prompt for better results
        system_prompt = """You are a world-class expert in pharmaceutical competitive intelligence and data validation systems. 

Your expertise includes:
- Radiopharmaceutical development pipelines
- Clinical trial processes and regulatory pathways
- Competitive intelligence methodologies
- Data validation and quality assurance
- Search strategy optimization for scientific and business intelligence

Generate precise, actionable configurations that reflect deep domain knowledge and practical validation requirements. Pay special attention to the nuances of pharmaceutical development stages, regulatory designations, and the specific requirements for tracking competitive intelligence in the radiopharmaceutical space."""

        # Define enhanced tool schema
        tool_schema = self._get_enhanced_config_schema()
        
        # Combine system prompt with user prompt
        full_prompt = f"{system_prompt}\n\n{prompt}"
        
        print(f"Calling Claude 4 API (strategy: {strategy})...")
        start_time = time.time()
        
        try:
            # Use shared AI API client with structured response
            response_data = await self.ai_client.call_structured_api(
                prompt=full_prompt,
                schema=tool_schema,
                model=self.model,
                tool_name="generate_config"
            )
            
            response_time = time.time() - start_time
            api_response = response_data['response']
            token_usage = response_data['token_usage']
            
            # Extract configuration from tool response
            config = self.ai_client.extract_structured_response(api_response, "generate_config")
            
            # Add metadata
            config_with_metadata = self._add_metadata(config, table_analysis, response_time, api_response, strategy, instruction_prompt, existing_config)
            
            print(f"SUCCESS: Config generated in {response_time:.2f}s")
            return config_with_metadata
            
        except Exception as e:
            print(f"ERROR: Claude API call failed: {str(e)}")
            raise
    
    def _build_standard_prompt(self, table_analysis, instruction_prompt, existing_config=None):
        """Build standard prompt using the base template"""
        # Load the base prompt from the markdown file
        prompt_loader = PromptLoader()
        base_prompt = prompt_loader.load_config_generation_prompt()
        
        if not base_prompt:
            raise ValueError("Could not load base config generation prompt")
        
        # Extract key information from table analysis
        table_context = self._build_table_context(table_analysis)
        
        return f"""
{base_prompt}

{table_context}

USER INSTRUCTIONS:
{instruction_prompt}

Please generate a complete column configuration following the schema and guidelines provided.
"""
    
    def _build_domain_expert_prompt(self, table_analysis, instruction_prompt, existing_config=None):
        """Build domain expert prompt with pharmaceutical-specific guidance"""
        table_context = self._build_table_context(table_analysis)
        
        return f"""
You are a pharmaceutical competitive intelligence expert specializing in radiopharmaceutical development tracking.

DOMAIN EXPERTISE CONTEXT:
- Radiopharmaceuticals combine radioactive isotopes with targeting molecules
- Key targets include FAP (Fibroblast Activation Protein), SSTR2 (Somatostatin Receptor 2), PSMA (Prostate-Specific Membrane Antigen)
- Development stages: Pre-clinical → Phase 1 → Phase 1/2 → Phase 2 → Phase 3 → BLA/NDA → Approval
- Regulatory designations: Fast Track, Breakthrough, Orphan Drug, Priority Review
- Key isotopes: Lu-177, Ac-225, Cu-64, Ga-68, Zr-89

COMPETITIVE INTELLIGENCE PRIORITIES:
1. Pipeline proximity to market (development stage)
2. Regulatory advantages (FDA/EMA designations)
3. Strategic partnerships and licensing deals
4. Clinical trial progress and setbacks
5. Target differentiation and competitive positioning

{table_context}

USER INSTRUCTIONS:
{instruction_prompt}

EXPERT GUIDANCE FOR CONFIGURATION:
- Product Name & Developer: CRITICAL for tracking (not just ID)
- Target & Indication: CRITICAL for competitive positioning
- Development Stage: CRITICAL for timeline assessment
- Regulatory designations: HIGH importance for competitive advantage
- Recent News: CRITICAL for real-time intelligence (use Claude 4 for complex analysis)
- Trial IDs: CRITICAL for tracking clinical progress
- Radionuclides: CRITICAL for technical differentiation

Generate a configuration that reflects pharmaceutical competitive intelligence best practices.
"""
    
    def _build_iterative_prompt(self, table_analysis, instruction_prompt, existing_config=None):
        """Build iterative prompt that considers existing config"""
        table_context = self._build_table_context(table_analysis)
        
        base_prompt = f"""
You are refining a pharmaceutical competitive intelligence configuration based on analysis and feedback.

{table_context}

USER INSTRUCTIONS:
{instruction_prompt}
"""
        
        if existing_config:
            base_prompt += f"""

EXISTING CONFIGURATION FOR REFERENCE:
{json.dumps(existing_config, indent=2)}

IMPROVEMENT OBJECTIVES:
1. Correct any importance level misalignments
2. Improve search group logic
3. Enhance model selection for complex fields
4. Refine examples and validation criteria
5. Optimize for pharmaceutical competitive intelligence workflows

Focus on iterative improvements while maintaining proven patterns.
"""
        
        return base_prompt
    
    def _build_competitive_intel_prompt(self, table_analysis, instruction_prompt, existing_config=None):
        """Build competitive intelligence focused prompt"""
        table_context = self._build_table_context(table_analysis)
        
        return f"""
You are configuring a competitive intelligence system for pharmaceutical product tracking.

COMPETITIVE INTELLIGENCE FRAMEWORK:
This system tracks competitive threats and opportunities in the radiopharmaceutical space. Each field serves a specific intelligence function:

STRATEGIC INTELLIGENCE FIELDS:
- Product identification: Enable tracking across multiple sources
- Target/indication mapping: Assess competitive overlap and differentiation
- Development timeline: Predict market entry and competitive timing
- Regulatory status: Identify competitive advantages and regulatory risks
- Partnership intelligence: Track strategic alliances and licensing deals
- News monitoring: Capture competitive developments and setbacks

VALIDATION STRATEGY:
- ID fields: Ensure consistent tracking across data sources
- CRITICAL fields: Core competitive intelligence (must be current and accurate)
- HIGH fields: Important for strategic decision-making
- MEDIUM fields: Useful context but not decision-critical
- LOW fields: Background information

SEARCH OPTIMIZATION:
- Group related fields that appear in similar sources
- Use Claude 4 for complex analysis (news, regulatory status)
- Use Perplexity for factual updates (trial status, partnerships)
- Optimize for speed vs accuracy based on business criticality

{table_context}

USER INSTRUCTIONS:
{instruction_prompt}

Generate a configuration optimized for pharmaceutical competitive intelligence workflows, ensuring each field serves a clear intelligence purpose.
"""
    
    def _build_table_context(self, table_analysis):
        """Build comprehensive table context for prompts"""
        basic_info = table_analysis['basic_info']
        column_analysis = table_analysis['column_analysis']
        domain_info = table_analysis['domain_info']
        groupings = table_analysis['inferred_groupings']
        
        context = f"""
TABLE ANALYSIS:
- File: {basic_info['filename']}
- Size: {basic_info['total_rows']} rows × {basic_info['total_columns']} columns
- Domain: {domain_info['inferred_domain']} (confidence: {domain_info['domain_confidence']})
- Purpose: {domain_info['inferred_purpose']}

COLUMN DETAILS:
"""
        
        for col_name, col_info in column_analysis.items():
            # Clean sample values for display
            clean_samples = []
            for val in col_info['sample_values'][:3]:
                clean_val = str(val).encode('ascii', 'ignore').decode('ascii')
                clean_samples.append(clean_val[:50] + '...' if len(clean_val) > 50 else clean_val)
            
            context += f"""
{col_name}:
  - Type: {col_info['data_type']}
  - Inferred Importance: {col_info['inferred_importance']}
  - Uniqueness: {col_info['unique_count']}/{col_info['total_count']} ({col_info['unique_percentage']:.1f}%)
  - Completeness: {col_info['total_count'] - col_info['null_count']}/{col_info['total_count']} ({100 - col_info['null_percentage']:.1f}%)
  - Sample Values: {clean_samples}
  - Format: {col_info['inferred_format']}
"""
        
        context += f"""
RECOMMENDED SEARCH GROUPS:
"""
        for group in groupings:
            context += f"""
Group {group['group_id']} - {group['group_name']}:
  - Columns: {', '.join(group['columns'])}
  - Reasoning: {group['reasoning']}
"""
        
        return context
    
    def _get_enhanced_config_schema(self):
        """Get enhanced JSON schema for config generation"""
        return {
            "type": "object",
            "properties": {
                "general_notes": {
                    "type": "string",
                    "description": "Comprehensive notes about the configuration, validation guidelines, and domain-specific considerations"
                },
                "default_model": {
                    "type": "string",
                    "description": "Default model to use for validation",
                    "default": "sonar-pro"
                },
                "default_search_context_size": {
                    "type": "string",
                    "enum": ["low", "high"],
                    "description": "Default search context size for Perplexity models",
                    "default": "low"
                },
                "search_groups": {
                    "type": "array",
                    "description": "Logical search group definitions for optimized batch processing",
                    "items": {
                        "type": "object",
                        "properties": {
                            "group_id": {"type": "integer", "minimum": 0},
                            "group_name": {"type": "string"},
                            "description": {"type": "string"},
                            "model": {"type": "string"},
                            "search_context": {"type": "string", "enum": ["low", "high"]}
                        },
                        "required": ["group_id", "group_name", "description", "model", "search_context"]
                    }
                },
                "validation_targets": {
                    "type": "array",
                    "description": "Detailed validation target configurations",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "description": {"type": "string"},
                            "importance": {"type": "string", "enum": ["ID", "CRITICAL", "HIGH", "MEDIUM", "LOW", "IGNORED"]},
                            "format": {"type": "string"},
                            "notes": {"type": "string", "description": "Detailed validation notes and formatting requirements"},
                            "examples": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                            "search_group": {"type": "integer", "minimum": 0},
                            "preferred_model": {"type": "string"},
                            "search_context_size": {"type": "string", "enum": ["low", "high"]}
                        },
                        "required": ["column", "description", "importance", "format", "notes", "examples", "search_group"]
                    }
                }
            },
            "required": ["general_notes", "validation_targets"]
        }
    
    
    def _add_metadata(self, config, table_analysis, response_time, claude_response, strategy, instruction_prompt=None, existing_config=None, interview_changes=None):
        """Add comprehensive metadata to the generated configuration with change tracking"""
        # Extract usage information
        usage = claude_response.get('usage', {})
        
        # Create change log entry
        change_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': 'modify_config' if existing_config else 'generate_config',
            'prompt_strategy': strategy,
            'user_instruction': instruction_prompt or "No specific instruction provided",
            'model_used': self.model,
            'response_time_seconds': response_time,
            'token_usage': {
                'input_tokens': usage.get('input_tokens', 0),
                'output_tokens': usage.get('output_tokens', 0),
                'total_tokens': usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
            }
        }
        
        # Add interview changes if provided
        if interview_changes:
            change_entry['interview_changes'] = interview_changes
        
        # If modifying existing config, preserve existing change log
        existing_change_log = []
        if existing_config and 'config_change_log' in existing_config:
            existing_change_log = existing_config['config_change_log']
        
        # Add current change to log
        change_log = existing_change_log + [change_entry]
        
        # Create comprehensive metadata
        metadata = {
            'generation_metadata': {
                'generated_at': datetime.now().isoformat(),
                'table_source': table_analysis['basic_info']['filename'],
                'domain': table_analysis['domain_info']['inferred_domain'],
                'prompt_strategy': strategy,
                'model_used': self.model,
                'response_time_seconds': response_time,
                'version': len(change_log),  # Version number based on change count
                'token_usage': {
                    'input_tokens': usage.get('input_tokens', 0),
                    'output_tokens': usage.get('output_tokens', 0),
                    'total_tokens': usage.get('input_tokens', 0) + usage.get('output_tokens', 0)
                }
            },
            'config_change_log': change_log
        }
        
        # Combine with generated config
        return {**metadata, **config}

# Standalone config validator - no external dependencies needed

class ConfigValidator:
    """Basic configuration validator for standalone operation"""
    
    def __init__(self):
        pass
    
    def validate_config(self, config):
        """Basic validation of configuration structure"""
        errors = []
        warnings = []
        
        # Check required sections
        if 'validation_targets' not in config:
            errors.append("Missing 'validation_targets' section")
        
        if 'search_groups' not in config:
            warnings.append("Missing 'search_groups' section")
        
        # Validate validation targets
        if 'validation_targets' in config:
            for i, target in enumerate(config['validation_targets']):
                if 'column' not in target:
                    errors.append(f"Validation target {i} missing 'column' field")
                if 'importance' not in target:
                    errors.append(f"Validation target {i} missing 'importance' field")
        
        return len(errors) == 0, errors, warnings

def analyze_config_quality(generated_config, existing_config_path):
    """Analyze the quality of generated configuration"""
    print("\n" + "="*60)
    print("CONFIGURATION QUALITY ANALYSIS")
    print("="*60)
    
    # Basic metrics
    targets = generated_config.get('validation_targets', [])
    groups = generated_config.get('search_groups', [])
    
    print(f"Configuration Structure:")
    print(f"  - Validation targets: {len(targets)}")
    print(f"  - Search groups: {len(groups)}")
    
    # Version and change tracking
    metadata = generated_config.get('generation_metadata', {})
    change_log = generated_config.get('config_change_log', [])
    
    print(f"  - Version: {metadata.get('version', 1)}")
    print(f"  - Change log entries: {len(change_log)}")
    
    # Importance distribution
    importance_counts = {}
    for target in targets:
        importance = target.get('importance', 'UNKNOWN')
        importance_counts[importance] = importance_counts.get(importance, 0) + 1
    
    print(f"  - Importance distribution: {importance_counts}")
    
    # Model usage
    model_usage = {}
    for target in targets:
        model = target.get('preferred_model', 'default')
        model_usage[model] = model_usage.get(model, 0) + 1
    
    print(f"  - Model usage: {model_usage}")
    
    # Notes quality
    general_notes = generated_config.get('general_notes', '')
    print(f"  - General notes length: {len(general_notes)} characters")
    
    # Search context usage
    context_usage = {}
    for target in targets:
        context = target.get('search_context_size', 'default')
        context_usage[context] = context_usage.get(context, 0) + 1
    
    print(f"  - Search context usage: {context_usage}")
    
    # Change log analysis
    if change_log:
        print(f"\nCHANGE LOG ANALYSIS:")
        total_tokens = 0
        total_time = 0
        
        for i, entry in enumerate(change_log, 1):
            action = entry.get('action', 'unknown')
            timestamp = entry.get('timestamp', 'unknown')
            strategy = entry.get('prompt_strategy', 'unknown')
            instruction = entry.get('user_instruction', 'No instruction')
            
            # Truncate long instructions
            if len(instruction) > 100:
                instruction = instruction[:100] + "..."
            
            print(f"  {i}. {timestamp} - {action}")
            print(f"     Strategy: {strategy}")
            print(f"     Instruction: {instruction}")
            
            # Token usage
            token_usage = entry.get('token_usage', {})
            tokens = token_usage.get('total_tokens', 0)
            time_taken = entry.get('response_time_seconds', 0)
            
            print(f"     Tokens: {tokens}, Time: {time_taken:.1f}s")
            
            total_tokens += tokens
            total_time += time_taken
        
        print(f"\nAGGREGATE METRICS:")
        print(f"  - Total tokens used: {total_tokens}")
        print(f"  - Total time spent: {total_time:.1f}s")
        print(f"  - Average tokens per change: {total_tokens / len(change_log):.1f}")
        print(f"  - Average time per change: {total_time / len(change_log):.1f}s")
    
    # Compare with existing if available
    if os.path.exists(existing_config_path):
        compare_with_existing_config(generated_config, existing_config_path)

def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Enhanced Config Generator Step 2: Claude 4 with Multiple Strategies',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--excel', 
                       default=DEFAULT_EXCEL,
                       help='Path to Excel file')
    
    parser.add_argument('--existing-config',
                       default=DEFAULT_CONFIG, 
                       help='Path to existing config for comparison')
    
    parser.add_argument('--sheet', 
                       help='Sheet name (optional)')
    
    parser.add_argument('--prompt', 
                       default="Generate a configuration for pharmaceutical competitive intelligence tracking with focus on radiopharmaceutical development pipelines",
                       help='Instruction prompt for config generation')
    
    parser.add_argument('--strategy',
                       choices=['standard', 'domain_expert', 'iterative', 'competitive_intelligence'],
                       default='competitive_intelligence',
                       help='Prompt strategy to use')
    
    parser.add_argument('--output', 
                       help='Output file for generated config (JSON)')
    
    parser.add_argument('--compare-all',
                       action='store_true',
                       help='Test all prompt strategies and compare results')
    
    parser.add_argument('--modify-existing',
                       action='store_true',
                       help='Modify existing config instead of generating new one')
    
    parser.add_argument('--api-key',
                       help='Claude API key (or set ANTHROPIC_API_KEY env var)')
    
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Verbose output')
    
    return parser.parse_args()

async def main():
    """Main function"""
    args = parse_arguments()
    
    print("ENHANCED CONFIG GENERATOR - STEP 2: CLAUDE 4 WITH PROMPT STRATEGIES")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Step 1: Analyze table
        print("\n1. ANALYZING TABLE...")
        analyzer = TableAnalyzer()
        table_analysis = analyzer.analyze_table(args.excel, args.sheet)
        
        # Print basic analysis summary
        basic_info = table_analysis['basic_info']
        domain_info = table_analysis['domain_info']
        print(f"   Table: {basic_info['filename']}")
        print(f"   Size: {basic_info['total_rows']} rows × {basic_info['total_columns']} columns")
        print(f"   Domain: {domain_info['inferred_domain']} (confidence: {domain_info['domain_confidence']})")
        
        # Initialize generator
        generator = EnhancedClaudeConfigGenerator(api_key=args.api_key)
        
        if args.compare_all:
            # Test all strategies
            print("\n2. TESTING ALL PROMPT STRATEGIES...")
            results = {}
            
            for strategy in ['standard', 'domain_expert', 'iterative', 'competitive_intelligence']:
                print(f"\n--- Testing {strategy} strategy ---")
                try:
                    config = await generator.generate_config_with_strategy(
                        table_analysis, 
                        args.prompt, 
                        strategy=strategy
                    )
                    results[strategy] = config
                    
                    # Quick validation
                    validator = ConfigValidator()
                    is_valid, errors, warnings = validator.validate_config(config)
                    print(f"   Validation: {'PASSED' if is_valid else 'FAILED'}")
                    
                except Exception as e:
                    print(f"   ERROR: {str(e)}")
                    results[strategy] = None
            
            # Compare results
            print(f"\n3. STRATEGY COMPARISON...")
            for strategy, config in results.items():
                if config:
                    metadata = config.get('generation_metadata', {})
                    targets = config.get('validation_targets', [])
                    print(f"   {strategy}: {len(targets)} targets, {metadata.get('response_time_seconds', 0):.1f}s")
                else:
                    print(f"   {strategy}: FAILED")
            
            # Save best result
            best_strategy = 'competitive_intelligence'  # Default preference
            if results.get(best_strategy):
                generated_config = results[best_strategy]
                
                if args.output:
                    output_path = Path(args.output)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(generated_config, f, indent=2, default=str)
                    
                    print(f"\n4. BEST RESULT SAVED: {output_path} (strategy: {best_strategy})")
        
        else:
            # Single strategy test
            action_type = "MODIFYING" if args.modify_existing else "GENERATING"
            print(f"\n2. {action_type} CONFIG WITH CLAUDE 4 (strategy: {args.strategy})...")
            
            # Load existing config if modifying or doing iterative
            existing_config = None
            if (args.modify_existing or args.strategy == 'iterative') and os.path.exists(args.existing_config):
                with open(args.existing_config, 'r') as f:
                    existing_config = json.load(f)
                    print(f"   Loaded existing config version {existing_config.get('generation_metadata', {}).get('version', 1)}")
            
            generated_config = await generator.generate_config_with_strategy(
                table_analysis, 
                args.prompt, 
                strategy=args.strategy,
                existing_config=existing_config
            )
            
            # Step 3: Validate generated config
            print("\n3. VALIDATING GENERATED CONFIG...")
            validator = ConfigValidator()
            is_valid, errors, warnings = validator.validate_config(generated_config)
            
            if is_valid:
                print("   SUCCESS: Configuration is valid!")
                if warnings:
                    print(f"   Warnings: {len(warnings)}")
                    for warning in warnings:
                        print(f"     - {warning}")
            else:
                print("   ERROR: Configuration validation failed!")
                for error in errors:
                    print(f"     - {error}")
            
            # Step 4: Quality analysis
            print("\n4. ANALYZING CONFIGURATION QUALITY...")
            analyze_config_quality(generated_config, args.existing_config)
            
            # Step 5: Save results
            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(generated_config, f, indent=2, default=str)
                
                print(f"\n5. RESULTS SAVED: {output_path}")
        
        # Final summary
        print("\n" + "="*60)
        print("GENERATION SUMMARY")
        print("="*60)
        
        if not args.compare_all:
            metadata = generated_config.get('generation_metadata', {})
            print(f"Strategy: {metadata.get('prompt_strategy', 'unknown')}")
            print(f"Model: {metadata.get('model_used', 'unknown')}")
            print(f"Response time: {metadata.get('response_time_seconds', 0):.2f}s")
            
            usage = metadata.get('token_usage', {})
            print(f"Tokens: {usage.get('input_tokens', 0)} in + {usage.get('output_tokens', 0)} out = {usage.get('total_tokens', 0)} total")
            
            targets = generated_config.get('validation_targets', [])
            groups = generated_config.get('search_groups', [])
            print(f"Validation targets: {len(targets)}")
            print(f"Search groups: {len(groups)}")
            
            print(f"Validation: {'PASSED' if is_valid else 'FAILED'}")
            
            if args.verbose:
                print("\nGenerated validation targets:")
                for target in targets:
                    print(f"  - {target['column']}: {target['importance']}")
        
        print("\nSUCCESS: Enhanced Step 2 completed successfully!")
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        if args.verbose:
            traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))