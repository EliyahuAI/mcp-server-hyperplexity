"""Change logging functionality."""

from typing import Dict, List, Optional, Tuple
import pandas as pd
from datetime import datetime
import json
from pathlib import Path
from rich.console import Console

console = Console()

class ChangeLogger:
    """Handles logging of changes made during validation."""
    
    def __init__(self, log_file: str = "change_log.xlsx"):
        self.log_file = Path(log_file)
        self.log_df = self._load_or_create_log()
        
    def _load_or_create_log(self) -> pd.DataFrame:
        """Load existing log or create new one."""
        if self.log_file.exists():
            return pd.read_excel(self.log_file)
            
        return pd.DataFrame(columns=[
            "timestamp",
            "sheet",
            "row_id",
            "column",
            "old_value",
            "new_value",
            "confidence",
            "status",
            "sources",
            "ai_model",
            "response_ms",
        ])
        
    def log_change(
        self,
        sheet: str,
        row_id: str,
        column: str,
        old_value: Optional[str],
        new_value: Optional[str],
        confidence: float,
        status: str,
        sources: List[str],
        ai_model: str,
        response_ms: float,
    ) -> None:
        """Log a single change."""
        new_row = {
            "timestamp": datetime.utcnow().isoformat(),
            "sheet": sheet,
            "row_id": row_id,
            "column": column,
            "old_value": old_value,
            "new_value": new_value,
            "confidence": confidence,
            "status": status,
            "sources": json.dumps(sources),
            "ai_model": ai_model,
            "response_ms": response_ms,
        }
        
        self.log_df = pd.concat([self.log_df, pd.DataFrame([new_row])], ignore_index=True)
        
    def save_log(self) -> None:
        """Save the log to Excel file."""
        # Create directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to Excel with formatting
        writer = pd.ExcelWriter(self.log_file, engine='xlsxwriter')
        self.log_df.to_excel(writer, index=False, sheet_name='Changes')
        
        # Get the workbook and worksheet objects
        workbook = writer.book
        worksheet = writer.sheets['Changes']
        
        # Add auto-filter
        worksheet.autofilter(0, 0, len(self.log_df), len(self.log_df.columns) - 1)
        
        # Add conditional formatting
        format_updated = workbook.add_format({'bg_color': '#00C851'})
        format_uncertain = workbook.add_format({'bg_color': '#FFEB3B'})
        format_override = workbook.add_format({'bg_color': '#FF9800'})
        format_forced = workbook.add_format({'bg_color': '#9E9E9E'})
        
        worksheet.conditional_format(
            1, 0, len(self.log_df), len(self.log_df.columns) - 1,
            {
                'type': 'text',
                'criteria': 'containing',
                'value': 'updated',
                'format': format_updated,
            }
        )
        worksheet.conditional_format(
            1, 0, len(self.log_df), len(self.log_df.columns) - 1,
            {
                'type': 'text',
                'criteria': 'containing',
                'value': 'uncertain',
                'format': format_uncertain,
            }
        )
        worksheet.conditional_format(
            1, 0, len(self.log_df), len(self.log_df.columns) - 1,
            {
                'type': 'text',
                'criteria': 'containing',
                'value': 'override',
                'format': format_override,
            }
        )
        worksheet.conditional_format(
            1, 0, len(self.log_df), len(self.log_df.columns) - 1,
            {
                'type': 'text',
                'criteria': 'containing',
                'value': 'forced',
                'format': format_forced,
            }
        )
        
        # Auto-adjust column widths
        for idx, col in enumerate(self.log_df.columns):
            max_len = max(
                self.log_df[col].astype(str).apply(len).max(),
                len(col)
            )
            worksheet.set_column(idx, idx, max_len + 2)
            
        writer.close() 