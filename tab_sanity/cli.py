"""Command-line interface for tab-sanity."""

import asyncio
import typer
from pathlib import Path
import yaml
from rich.console import Console
from rich.progress import Progress
from typing import Optional
import pandas as pd
import os

from .config import Config
from .loader import load_spreadsheet
from .validator import Validator
from .schema_validator import SchemaValidator
from .parallel_validator import ParallelValidator
from .logger import ChangeLogger

app = typer.Typer()
console = Console()

def load_config(config_path: str) -> Config:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        config_data = yaml.safe_load(f)
    return Config(**config_data)

@app.command()
def validate(
    config_path: str = typer.Argument(..., help="Path to config YAML file"),
    dry_run: bool = typer.Option(False, help="Simulate changes without writing to file"),
    verbose: int = typer.Option(0, "-v", count=True, help="Increase verbosity"),
    use_schema: bool = typer.Option(False, "--schema", help="Use JSON schema for structured API responses"),
    parallel: Optional[int] = typer.Option(None, "--parallel", "-p", help="Enable parallel processing with specified number of concurrent rows (default: 5)"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Perplexity API key (defaults to PERPLEXITY_API_KEY env var)"),
):
    """Validate spreadsheet using AI."""
    try:
        # Load configuration
        config = load_config(config_path)
        if dry_run:
            config.dry_run = True
            console.print("[yellow]Running in dry-run mode - no changes will be written[/yellow]")
            
        # Get API key from environment or option
        if not api_key:
            api_key = os.environ.get("PERPLEXITY_API_KEY")
            if not api_key:
                console.print("[red]Error: No API key provided. Set PERPLEXITY_API_KEY env var or use --api-key.[/red]")
                raise typer.Exit(1)
        
        # Load spreadsheet
        df = load_spreadsheet(config.spreadsheet, config.sheet)
        
        # Initialize validator and logger
        if parallel is not None:
            # Use parallel validator with specified concurrency
            concurrent_rows = parallel if parallel > 0 else 5
            console.print(f"[cyan]Using ParallelValidator with {concurrent_rows} concurrent rows[/cyan]")
            validator = ParallelValidator(config, api_key=api_key, max_concurrent_rows=concurrent_rows)
        elif use_schema:
            console.print("[cyan]Using SchemaValidator with JSON schema enforcement[/cyan]")
            validator = SchemaValidator(config, api_key=api_key)
        else:
            console.print("[cyan]Using standard Validator[/cyan]")
            validator = Validator(config, api_key=api_key)
            
        logger = ChangeLogger(config.log_file)
        
        # Run validation
        results, updated_df = asyncio.run(validator.validate_dataframe(df))
        
        # Process results and update spreadsheet
        if not config.dry_run:
            # Save the updated DataFrame with validation results
            updated_df.to_excel(config.spreadsheet, sheet_name=config.sheet, index=False)
            console.print(f"[green]Updated spreadsheet saved to {config.spreadsheet}[/green]")
            
            # Create detailed change log
            for row_key, column_results in results.items():
                for column, (new_value, confidence, sources, confidence_level) in column_results.items():
                    if new_value is not None and column not in ["Last Check", "Next Check Date"]:
                        # Find the corresponding row in the original dataframe
                        row_parts = row_key.split('|')
                        mask = df[config.primary_key[0]] == row_parts[0]
                        if len(config.primary_key) > 1 and len(row_parts) > 1:
                            mask &= df[config.primary_key[1]] == row_parts[1]
                            
                        if not mask.any():
                            continue  # Skip if row not found
                            
                        row_idx = df[mask].index[0]
                        
                        # Get current value
                        current_value = df.at[row_idx, column]
                        
                        # Only log if value has changed
                        if str(current_value) != str(new_value):
                            # Log change
                            logger.log_change(
                                sheet=config.sheet,
                                row_id=row_key,
                                column=column,
                                old_value=str(current_value),
                                new_value=str(new_value),
                                confidence=confidence,
                                status="updated" if confidence >= 0.8 else "uncertain",
                                sources=sources,
                                ai_model=validator.model_name,
                                response_ms=0.0,  # TODO: Track actual response time
                            )
            
            logger.save_log()
            
        console.print("[green]Validation complete![/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def override(
    config_path: str = typer.Argument(..., help="Path to config YAML file"),
    row_id: str = typer.Argument(..., help="Row identifier (e.g. 'ICML|2025')"),
    column: str = typer.Argument(..., help="Column to override"),
    value: str = typer.Argument(..., help="New value"),
):
    """Override a cell value manually."""
    try:
        config = load_config(config_path)
        df = load_spreadsheet(config.spreadsheet, config.sheet)
        
        # Find the row
        row_parts = row_id.split('|')
        mask = df[config.primary_key[0]] == row_parts[0]
        if len(row_parts) > 1:
            mask &= df[config.primary_key[1]] == row_parts[1]
            
        if not mask.any():
            raise ValueError(f"Row not found: {row_id}")
            
        row_idx = df[mask].index[0]
        col_idx = df.columns.get_loc(column)
        
        # Get current value
        current_value = df.at[row_idx, column]
        
        # Update dataframe
        df.at[row_idx, column] = value
        
        # Save updated dataframe
        df.to_excel(config.spreadsheet, sheet_name=config.sheet, index=False)
        
        # Log the override
        logger = ChangeLogger(config.log_file)
        logger.log_change(
            sheet=config.sheet,
            row_id=row_id,
            column=column,
            old_value=str(current_value),
            new_value=value,
            confidence=1.0,
            status="override",
            sources=[],
            ai_model="manual",
            response_ms=0.0,
        )
        logger.save_log()
        
        console.print("[green]Override applied successfully![/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

@app.command()
def force_update(
    config_path: str = typer.Argument(..., help="Path to config YAML file"),
    column: str = typer.Argument(..., help="Column to force update"),
    filter_expr: Optional[str] = typer.Option(None, help="Filter expression (e.g. 'Year==2023')"),
    use_schema: bool = typer.Option(False, "--schema", help="Use JSON schema for structured API responses"),
    parallel: Optional[int] = typer.Option(None, "--parallel", "-p", help="Enable parallel processing with specified number of concurrent rows (default: 5)"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="Perplexity API key (defaults to PERPLEXITY_API_KEY env var)"),
):
    """Force update a column, ignoring existing values."""
    try:
        config = load_config(config_path)
        df = load_spreadsheet(config.spreadsheet, config.sheet)
        
        # Get API key from environment or option
        if not api_key:
            api_key = os.environ.get("PERPLEXITY_API_KEY")
            if not api_key:
                console.print("[red]Error: No API key provided. Set PERPLEXITY_API_KEY env var or use --api-key.[/red]")
                raise typer.Exit(1)
        
        # Apply filter if provided
        if filter_expr:
            df = df.query(filter_expr)
            
        # Initialize validator and logger
        if parallel is not None:
            # Use parallel validator with specified concurrency
            concurrent_rows = parallel if parallel > 0 else 5
            console.print(f"[cyan]Using ParallelValidator with {concurrent_rows} concurrent rows[/cyan]")
            validator = ParallelValidator(config, api_key=api_key, max_concurrent_rows=concurrent_rows)
        elif use_schema:
            console.print("[cyan]Using SchemaValidator with JSON schema enforcement[/cyan]")
            validator = SchemaValidator(config, api_key=api_key)
        else:
            console.print("[cyan]Using standard Validator[/cyan]")
            validator = Validator(config, api_key=api_key)
            
        # Force recheck for the specified column
        config.recheck.force_recheck = True
        
        logger = ChangeLogger(config.log_file)
        
        # Override the recheck configuration to only validate the specified column
        config.recheck.recheck_columns = [column]
        
        # Run validation only on filtered rows and the specific column
        results, updated_df = asyncio.run(validator.validate_dataframe(df))
        
        # Save the updated dataframe
        df.to_excel(config.spreadsheet, sheet_name=config.sheet, index=False)
        
        # Process results and log changes
        for row_key, column_results in results.items():
            if column in column_results:
                new_value, confidence, sources, confidence_level = column_results[column]
                if new_value is not None:
                    # Find the row in the original dataframe
                    row_parts = row_key.split('|')
                    mask = df[config.primary_key[0]] == row_parts[0]
                    if len(config.primary_key) > 1 and len(row_parts) > 1:
                        mask &= df[config.primary_key[1]] == row_parts[1]
                        
                    if not mask.any():
                        continue  # Skip if row not found
                        
                    row_idx = df[mask].index[0]
                    
                    # Get current value before update
                    current_value = df.at[row_idx, column]
                    
                    # Log change
                    logger.log_change(
                        sheet=config.sheet,
                        row_id=row_key,
                        column=column,
                        old_value=str(current_value),
                        new_value=str(new_value),
                        confidence=confidence,
                        status="forced",
                        sources=sources,
                        ai_model=validator.model_name,
                        response_ms=0.0,
                    )
        
        logger.save_log()
        console.print("[green]Force update complete![/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

if __name__ == "__main__":
    app() 