"""Configuration models for tab-sanity."""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import yaml
import logging

class ValidationType(str, Enum):
    """Types of validation supported."""
    STRING = "string"
    DATE = "date"
    URL = "url"
    EMAIL = "email"
    PHONE = "phone"
    NUMBER = "number"
    BOOLEAN = "boolean"
    FREQUENCY = "frequency"  # For conference frequency
    IMPACT = "impact"  # For impact factor
    ATTENDANCE = "attendance"  # For number of attendees

class ColumnImportance(str, Enum):
    """Importance level of a column."""
    CRITICAL = "critical"  # Must be accurate and up-to-date
    INTERESTING = "interesting"  # Good to have but not essential
    IGNORED = "ignored"  # Can be ignored in validation

class ValidationTarget(BaseModel):
    """Configuration for a column to validate."""
    column: str
    type: ValidationType
    importance: ColumnImportance = Field(ColumnImportance.INTERESTING)  # Default to interesting

class ColorMap(BaseModel):
    """Color mapping for confidence levels."""
    high: str = "00C851"  # Green
    medium: str = "FFEB3B"  # Yellow
    low: str = "FF4444"  # Red
    forced: str = "9E9E9E"  # Gray

class RecheckConfig(BaseModel):
    """Configuration for rechecking data."""
    enabled: bool = True
    min_days_between_checks: int = 30
    max_days_between_checks: int = 365
    force_recheck: bool = False
    recheck_columns: List[str] = []  # Specific columns to force recheck
    recheck_thresholds: Dict[str, float] = {}  # Column-specific confidence thresholds for recheck

class Config(BaseModel):
    """Main configuration model."""
    spreadsheet: str
    sheet: str
    primary_key: List[str]
    validation_targets: List[ValidationTarget]
    website_column: Optional[str] = None
    fallback_search: bool = True
    log_file: str = "change_log.xlsx"
    dry_run: bool = False
    recheck: RecheckConfig = RecheckConfig()
    
    @classmethod
    def from_table_directory(cls, spreadsheet: str, sheet: str) -> 'Config':
        """Create a Config instance from a table directory."""
        # Get the directory containing the spreadsheet
        table_dir = os.path.dirname(spreadsheet)
        config_path = os.path.join(table_dir, "column_config.yml")
        
        # Read the column configuration
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                column_config = yaml.safe_load(f)
        else:
            # If no config exists, create a template
            column_config = {
                "primary_key": ["Conference", "Start Date"],  # Default primary key for conferences
                "website_column": "Website",  # Default website column
                "columns": {}  # Empty columns config
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(column_config, f, default_flow_style=False)
            logging.info(f"Created column config template at {config_path}")
            return None  # Return None to indicate config needs to be filled in
        
        # Create validation targets from the config
        validation_targets = []
        website_column = None
        for column, config in column_config["columns"].items():
            # Handle both old and new config formats
            if "type" in config:
                val_type = ValidationType(config["type"])
            else:
                # Map old format to new format
                format_map = {
                    "String": ValidationType.STRING,
                    "URL": ValidationType.URL,
                    "YYYY-MM-DD": ValidationType.DATE,
                    "Boolean": ValidationType.BOOLEAN,
                    "Number": ValidationType.NUMBER,
                    "City, Country": ValidationType.STRING
                }
                val_type = format_map.get(config.get("format", "String"), ValidationType.STRING)
                
                # Check if this is a website column
                if config.get("format") == "URL":
                    website_column = column
            
            if "importance" in config:
                importance = ColumnImportance(config["importance"].lower())
            else:
                importance = ColumnImportance.INTERESTING
                
            validation_targets.append(ValidationTarget(
                column=column,
                type=val_type,
                importance=importance
            ))
        
        # Get primary key from config or use defaults
        primary_key = column_config.get("primary_key", ["Conference", "Start Date"])
        
        # Get website column from config or use detected one
        website_column = column_config.get("website_column", website_column)
        
        return cls(
            spreadsheet=spreadsheet,
            sheet=sheet,
            primary_key=primary_key,
            validation_targets=validation_targets,
            website_column=website_column,
            fallback_search=True,
            log_file=os.path.join(table_dir, "change_log.xlsx"),
            dry_run=False,
            recheck=RecheckConfig()
        )

    @classmethod
    def get_default_targets(cls) -> List[ValidationTarget]:
        """Get default validation targets for all columns."""
        return [
            ValidationTarget(column="Conference", type=ValidationType.STRING, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="Indication", type=ValidationType.STRING, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="Website", type=ValidationType.URL, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="Sponsoring Society", type=ValidationType.STRING, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Frequency", type=ValidationType.FREQUENCY, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="Start Date", type=ValidationType.DATE, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="End Date", type=ValidationType.DATE, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="Location", type=ValidationType.STRING, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="Abstract Submission Deadline", type=ValidationType.DATE, importance=ColumnImportance.CRITICAL),
            ValidationTarget(column="Notification Date", type=ValidationType.DATE, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Late Breaker Option", type=ValidationType.BOOLEAN, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Late Breaker Deadline", type=ValidationType.DATE, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Encores Allowed?", type=ValidationType.BOOLEAN, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Publication", type=ValidationType.STRING, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Impact Factor", type=ValidationType.IMPACT, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Number of Attendees", type=ValidationType.ATTENDANCE, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Submitter/Presenter", type=ValidationType.STRING, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Poster Upload Date", type=ValidationType.DATE, importance=ColumnImportance.INTERESTING),
            ValidationTarget(column="Poster Guidelines", type=ValidationType.STRING, importance=ColumnImportance.IGNORED),
            ValidationTarget(column="Industry Restrictions", type=ValidationType.STRING, importance=ColumnImportance.INTERESTING)
        ] 