#!/usr/bin/env python3
"""
Interactive CLI Demo for Table Generation System

Demonstrates conversational table design with AI assistance.
Features:
- Start new table design conversations
- Iterative refinement with user feedback
- Row expansion capabilities
- CSV and config generation
- Conversation history tracking
"""

import os
import sys
import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from table_maker.src.conversation_handler import TableConversationHandler
from table_maker.src.table_generator import TableGenerator
from table_maker.src.row_expander import RowExpander
from table_maker.src.config_generator import ConfigGenerator
from table_maker.src.prompt_loader import PromptLoader
from table_maker.src.schema_validator import SchemaValidator
from src.shared.ai_api_client import AIAPIClient


# ASCII art banner
BANNER = """
==============================================================================
    TABLE GENERATION SYSTEM - INTERACTIVE DEMO
==============================================================================
    Design research tables through natural conversation with AI
==============================================================================
"""


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_banner():
    """Print welcome banner."""
    print(f"{Colors.CYAN}{BANNER}{Colors.ENDC}")


def print_section(title: str):
    """Print section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title:^80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*80}{Colors.ENDC}\n")


def print_success(message: str):
    """Print success message."""
    print(f"{Colors.GREEN}[SUCCESS]{Colors.ENDC} {message}")


def print_error(message: str):
    """Print error message."""
    print(f"{Colors.RED}[ERROR]{Colors.ENDC} {message}")


def print_warning(message: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}[WARNING]{Colors.ENDC} {message}")


def print_info(message: str):
    """Print info message."""
    print(f"{Colors.CYAN}[INFO]{Colors.ENDC} {message}")


def print_ai_response(message: str):
    """Print AI response with formatting."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}AI:{Colors.ENDC} {message}\n")


def print_table_structure(proposal: Dict[str, Any]):
    """Print current table structure in readable format."""
    print(f"\n{Colors.BOLD}{Colors.YELLOW}Current Table Structure:{Colors.ENDC}")
    print(f"{Colors.YELLOW}{'─'*80}{Colors.ENDC}")

    columns = proposal.get('columns', [])
    rows_data = proposal.get('rows', {})

    # Print columns
    print(f"\n{Colors.BOLD}Columns ({len(columns)}):{Colors.ENDC}")
    for col in columns:
        is_id = col.get('is_identification', False)
        id_marker = f"{Colors.CYAN}[ID]{Colors.ENDC} " if is_id else ""
        importance = col.get('importance', 'N/A')

        print(f"  {id_marker}{Colors.BOLD}{col['name']}{Colors.ENDC}")
        print(f"    Description: {col.get('description', 'N/A')}")
        print(f"    Format: {col.get('format', 'String')} | Importance: {importance}")

    # Print sample rows
    sample_rows = rows_data.get('sample_rows', [])
    print(f"\n{Colors.BOLD}Sample Rows ({len(sample_rows)}):{Colors.ENDC}")
    if sample_rows:
        for idx, row in enumerate(sample_rows[:3], 1):  # Show first 3 rows
            print(f"  Row {idx}:")
            for key, value in row.items():
                display_value = str(value)[:50] + "..." if len(str(value)) > 50 else value
                print(f"    {key}: {display_value}")
        if len(sample_rows) > 3:
            print(f"  ... and {len(sample_rows) - 3} more rows")
    else:
        print("  No sample rows yet")

    print(f"{Colors.YELLOW}{'─'*80}{Colors.ENDC}\n")


def print_menu():
    """Print main menu options."""
    print(f"\n{Colors.BOLD}Available Commands:{Colors.ENDC}")
    print(f"  {Colors.GREEN}continue{Colors.ENDC} - Provide feedback to refine the table")
    print(f"  {Colors.GREEN}expand{Colors.ENDC}   - Expand rows with additional samples")
    print(f"  {Colors.GREEN}generate{Colors.ENDC} - Generate CSV and config files")
    print(f"  {Colors.GREEN}show{Colors.ENDC}     - Show current table structure")
    print(f"  {Colors.GREEN}history{Colors.ENDC}  - View conversation history")
    print(f"  {Colors.GREEN}new{Colors.ENDC}      - Start a new conversation")
    print(f"  {Colors.GREEN}quit{Colors.ENDC}     - Exit the demo")
    print()


class TableMakerCLI:
    """Interactive CLI for table generation system."""

    def __init__(self):
        """Initialize CLI components."""
        self.output_dir = Path(__file__).parent / "output"
        self.output_dir.mkdir(exist_ok=True)

        # Initialize logging
        self._setup_logging()

        # Initialize components
        self.ai_client = None
        self.conversation_handler = None
        self.table_generator = TableGenerator()
        self.row_expander = None
        self.config_generator = None

        self.conversation_active = False
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _setup_logging(self):
        """Configure logging."""
        log_dir = self.output_dir / "logs"
        log_dir.mkdir(exist_ok=True)

        log_file = log_dir / f"cli_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stderr)
            ]
        )

        # Reduce noise from some loggers
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)

    def check_api_key(self) -> bool:
        """Check for ANTHROPIC_API_KEY in environment."""
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            print_error("ANTHROPIC_API_KEY not found in environment variables")
            print_info("Please set your API key:")
            print_info("  export ANTHROPIC_API_KEY='your-api-key-here'")
            return False

        print_success("ANTHROPIC_API_KEY found")
        return True

    def initialize_components(self) -> bool:
        """Initialize AI client and conversation handler."""
        try:
            print_info("Initializing components...")

            # Initialize AI client
            self.ai_client = AIAPIClient()

            # Initialize prompt loader and schema validator
            prompts_dir = Path(__file__).parent / "prompts"
            schemas_dir = Path(__file__).parent / "schemas"

            prompt_loader = PromptLoader(str(prompts_dir))
            schema_validator = SchemaValidator(str(schemas_dir))

            # Initialize handlers
            self.conversation_handler = TableConversationHandler(
                self.ai_client,
                prompt_loader,
                schema_validator
            )

            self.row_expander = RowExpander(
                self.ai_client,
                prompt_loader,
                schema_validator
            )

            self.config_generator = ConfigGenerator(self.ai_client)

            print_success("Components initialized successfully")
            return True

        except Exception as e:
            print_error(f"Failed to initialize components: {e}")
            logging.exception("Initialization error")
            return False

    async def start_conversation(self):
        """Start a new table design conversation."""
        print_section("Start New Conversation")

        print("Describe your research table. What data do you want to collect?")
        print("Be specific about the purpose, columns, and type of data.\n")

        user_input = input(f"{Colors.BOLD}Your description: {Colors.ENDC}").strip()

        if not user_input:
            print_warning("No input provided. Returning to menu.")
            return

        print_info("Sending request to AI (this may take a moment)...")

        try:
            result = await self.conversation_handler.start_conversation(
                user_message=user_input,
                model="claude-sonnet-4-5"
            )

            if not result['success']:
                print_error(f"Failed to start conversation: {result.get('error')}")
                return

            self.conversation_active = True

            # Display AI response
            print_ai_response(result['ai_message'])

            # Show proposed table
            print_table_structure(result['proposed_table'])

            # Check if ready to generate
            if result['ready_to_generate']:
                print_success("Table design is ready! You can use 'generate' to create files.")
            else:
                print_info("Continue refining the table design with feedback.")

        except Exception as e:
            print_error(f"Error starting conversation: {e}")
            logging.exception("Conversation start error")

    async def continue_conversation(self):
        """Continue conversation with feedback."""
        if not self.conversation_active:
            print_warning("No active conversation. Start a new one first.")
            return

        print_section("Continue Conversation")

        print("Provide feedback or request changes to the table design.")
        print("Examples:")
        print("  - Add a column for 'publication date'")
        print("  - Change importance of 'impact factor' to HIGH")
        print("  - The table looks good, I'm ready to generate it\n")

        user_input = input(f"{Colors.BOLD}Your feedback: {Colors.ENDC}").strip()

        if not user_input:
            print_warning("No input provided.")
            return

        print_info("Processing feedback (this may take a moment)...")

        try:
            result = await self.conversation_handler.continue_conversation(
                user_message=user_input,
                model="claude-sonnet-4-5"
            )

            if not result['success']:
                print_error(f"Failed to continue conversation: {result.get('error')}")
                return

            # Display AI response
            print_ai_response(result['ai_message'])

            # Show updated table
            print_table_structure(result['proposed_table'])

            # Check if ready to generate
            if result['ready_to_generate']:
                print_success("Table design is ready! You can use 'generate' to create files.")
            else:
                print_info("Continue refining or use 'generate' when satisfied.")

        except Exception as e:
            print_error(f"Error continuing conversation: {e}")
            logging.exception("Conversation continue error")

    async def expand_rows(self):
        """Expand table rows with additional samples."""
        if not self.conversation_active:
            print_warning("No active conversation. Start a new one first.")
            return

        current_proposal = self.conversation_handler.get_current_proposal()
        if not current_proposal:
            print_error("No table proposal available.")
            return

        print_section("Expand Rows")

        print("Describe what kind of rows you want to add.")
        print("Examples:")
        print("  - Add 5 more examples of machine learning papers")
        print("  - Generate 10 rows covering different research areas")
        print("  - Add samples for papers published in 2024\n")

        expansion_request = input(f"{Colors.BOLD}Expansion request: {Colors.ENDC}").strip()

        if not expansion_request:
            print_warning("No input provided.")
            return

        # Ask for row count
        try:
            row_count_input = input(f"{Colors.BOLD}Number of rows to generate (default: 10): {Colors.ENDC}").strip()
            row_count = int(row_count_input) if row_count_input else 10
        except ValueError:
            print_warning("Invalid number, using default of 10")
            row_count = 10

        print_info(f"Generating {row_count} new rows (this may take a moment)...")

        try:
            # Get current table structure
            table_structure = self.conversation_handler.get_table_structure()
            existing_rows = current_proposal.get('rows', {}).get('sample_rows', [])

            result = await self.row_expander.expand_rows(
                table_structure=current_proposal,
                existing_rows=existing_rows,
                expansion_request=expansion_request,
                row_count=row_count,
                model="claude-sonnet-4-5"
            )

            if not result['success']:
                print_error(f"Failed to expand rows: {result.get('error')}")
                return

            expanded_rows = result['expanded_rows']
            print_success(f"Generated {len(expanded_rows)} new rows")

            # Show reasoning
            print(f"\n{Colors.CYAN}AI Reasoning:{Colors.ENDC}")
            print(result['reasoning'])

            # Merge rows
            merge_result = self.row_expander.merge_expanded_rows(
                existing_rows=existing_rows,
                expanded_rows=expanded_rows,
                deduplicate=True
            )

            # Update conversation handler's current proposal
            current_proposal['rows']['sample_rows'] = merge_result['merged_rows']

            print_success(
                f"Merged rows: {merge_result['total_count']} total "
                f"({merge_result['duplicates_removed']} duplicates removed)"
            )

            # Show sample of new rows
            print(f"\n{Colors.BOLD}Sample of expanded rows:{Colors.ENDC}")
            for idx, row in enumerate(expanded_rows[:2], 1):
                print(f"  Row {idx}:")
                for key, value in row.items():
                    display_value = str(value)[:60] + "..." if len(str(value)) > 60 else value
                    print(f"    {key}: {display_value}")

        except Exception as e:
            print_error(f"Error expanding rows: {e}")
            logging.exception("Row expansion error")

    async def generate_outputs(self):
        """Generate CSV and config files."""
        if not self.conversation_active:
            print_warning("No active conversation. Start a new one first.")
            return

        if not self.conversation_handler.is_ready_to_generate():
            print_warning("Table design is not marked as ready.")
            print_info("You can still generate, but consider refining the design first.")

            confirm = input(f"{Colors.BOLD}Generate anyway? (y/n): {Colors.ENDC}").strip().lower()
            if confirm != 'y':
                return

        print_section("Generate Outputs")

        try:
            # Get table structure
            table_structure = self.conversation_handler.get_table_structure()

            # Generate filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"table_{timestamp}.csv"
            config_filename = f"config_{timestamp}.json"
            conversation_filename = f"conversation_{timestamp}.json"

            csv_path = self.output_dir / csv_filename
            config_path = self.output_dir / config_filename
            conversation_path = self.output_dir / conversation_filename

            # Generate CSV
            print_info("Generating CSV file...")
            csv_result = self.table_generator.generate_csv(
                columns=table_structure['columns'],
                rows=table_structure['rows'],
                output_path=str(csv_path),
                include_metadata=True
            )

            if csv_result['success']:
                print_success(
                    f"CSV generated: {csv_path}\n"
                    f"  Rows: {csv_result['row_count']}, Columns: {csv_result['column_count']}"
                )
            else:
                print_error(f"CSV generation failed: {csv_result.get('error')}")

            # Generate config
            print_info("Generating validation config...")
            config_result = await self.config_generator.generate_config_from_table(
                table_structure=table_structure,
                conversation_history=self.conversation_handler.get_conversation_history(),
                model="claude-sonnet-4-5"
            )

            if config_result['success']:
                # Export config to file
                export_result = self.config_generator.export_config_to_file(
                    config=config_result['config'],
                    output_path=str(config_path)
                )

                if export_result['success']:
                    print_success(f"Config generated: {config_path}")
                else:
                    print_error(f"Config export failed: {export_result.get('error')}")
            else:
                print_error(f"Config generation failed: {config_result.get('error')}")

            # Save conversation history
            print_info("Saving conversation history...")
            save_result = self.conversation_handler.save_conversation(
                output_path=str(conversation_path)
            )

            if save_result['success']:
                print_success(f"Conversation saved: {conversation_path}")
            else:
                print_error(f"Conversation save failed: {save_result.get('error')}")

            # Summary
            print_section("Generation Summary")
            print_success("All outputs generated successfully!")
            print(f"\n{Colors.BOLD}Output files:{Colors.ENDC}")
            print(f"  CSV:          {csv_path}")
            print(f"  Config:       {config_path}")
            print(f"  Conversation: {conversation_path}")
            print(f"\n{Colors.BOLD}Output directory:{Colors.ENDC} {self.output_dir}")

        except Exception as e:
            print_error(f"Error generating outputs: {e}")
            logging.exception("Output generation error")

    def show_table(self):
        """Display current table structure."""
        if not self.conversation_active:
            print_warning("No active conversation. Start a new one first.")
            return

        current_proposal = self.conversation_handler.get_current_proposal()
        if not current_proposal:
            print_error("No table proposal available.")
            return

        print_section("Current Table Structure")
        print_table_structure(current_proposal)

    def show_history(self):
        """Display conversation history."""
        if not self.conversation_active:
            print_warning("No active conversation. Start a new one first.")
            return

        history = self.conversation_handler.get_conversation_history()
        if not history:
            print_warning("No conversation history available.")
            return

        print_section("Conversation History")

        for idx, msg in enumerate(history, 1):
            role = msg['role'].upper()
            timestamp = msg['timestamp']
            content = msg['content']

            if role == 'USER':
                print(f"{Colors.BOLD}Turn {idx} - USER:{Colors.ENDC} ({timestamp})")
                print(f"  {content}\n")
            else:
                print(f"{Colors.BOLD}Turn {idx} - ASSISTANT:{Colors.ENDC} ({timestamp})")
                ai_message = content.get('ai_message', '') if isinstance(content, dict) else content
                print(f"  {ai_message}\n")

    def new_conversation(self):
        """Reset and start fresh."""
        if self.conversation_active:
            confirm = input(
                f"{Colors.YELLOW}This will discard the current conversation. Continue? (y/n): {Colors.ENDC}"
            ).strip().lower()
            if confirm != 'y':
                return

        self.conversation_handler.reset_conversation()
        self.conversation_active = False
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        print_success("Ready for a new conversation!")

    async def run(self):
        """Run the interactive CLI."""
        print_banner()

        # Check API key
        if not self.check_api_key():
            return

        # Initialize components
        if not self.initialize_components():
            return

        print_success("System ready!")
        print_info(f"Output directory: {self.output_dir}")
        print_info("Type 'quit' to exit at any time")

        # Main loop
        while True:
            try:
                if not self.conversation_active:
                    print(f"\n{Colors.BOLD}Start a new conversation to begin designing a table.{Colors.ENDC}")
                    print(f"Type {Colors.GREEN}'new'{Colors.ENDC} to start or {Colors.GREEN}'quit'{Colors.ENDC} to exit.\n")
                    command = input(f"{Colors.BOLD}> {Colors.ENDC}").strip().lower()

                    if command == 'quit':
                        break
                    elif command == 'new':
                        await self.start_conversation()
                    else:
                        print_warning("Please type 'new' to start or 'quit' to exit.")
                else:
                    print_menu()
                    command = input(f"{Colors.BOLD}> {Colors.ENDC}").strip().lower()

                    if command == 'quit':
                        break
                    elif command == 'continue':
                        await self.continue_conversation()
                    elif command == 'expand':
                        await self.expand_rows()
                    elif command == 'generate':
                        await self.generate_outputs()
                    elif command == 'show':
                        self.show_table()
                    elif command == 'history':
                        self.show_history()
                    elif command == 'new':
                        self.new_conversation()
                    else:
                        print_warning(f"Unknown command: {command}")

            except KeyboardInterrupt:
                print(f"\n\n{Colors.YELLOW}Interrupted by user{Colors.ENDC}")
                confirm = input(f"{Colors.BOLD}Exit? (y/n): {Colors.ENDC}").strip().lower()
                if confirm == 'y':
                    break

            except Exception as e:
                print_error(f"Unexpected error: {e}")
                logging.exception("Main loop error")

        print(f"\n{Colors.CYAN}Thank you for using the Table Generation System!{Colors.ENDC}\n")


def main():
    """Main entry point."""
    try:
        cli = TableMakerCLI()
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Exiting...{Colors.ENDC}\n")
    except Exception as e:
        print_error(f"Fatal error: {e}")
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
