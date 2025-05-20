"""Spreadsheet loading functionality."""

import pandas as pd
from typing import Union, Optional
from pathlib import Path
import httpx
from rich.console import Console
from rich.progress import Progress

console = Console()

def load_spreadsheet(
    file_path: Union[str, Path],
    sheet_name: Optional[str] = None,
    is_google_sheet: bool = False,
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load a spreadsheet into a pandas DataFrame.
    
    Args:
        file_path: Path to the spreadsheet file or Google Sheet ID
        sheet_name: Name of the sheet to load (optional)
        is_google_sheet: Whether the input is a Google Sheet
        api_key: Google Sheets API key if using Google Sheets
        
    Returns:
        pandas DataFrame containing the spreadsheet data
    """
    if is_google_sheet:
        if not api_key:
            raise ValueError("API key required for Google Sheets")
        return _load_google_sheet(file_path, sheet_name, api_key)
    
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Spreadsheet file not found: {file_path}")
    
    if file_path.suffix.lower() in ['.xlsx', '.xls']:
        return pd.read_excel(file_path, sheet_name=sheet_name)
    elif file_path.suffix.lower() == '.csv':
        return pd.read_csv(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")

def _load_google_sheet(
    sheet_id: str,
    sheet_name: Optional[str],
    api_key: str,
) -> pd.DataFrame:
    """Load data from a Google Sheet."""
    base_url = "https://sheets.googleapis.com/v4/spreadsheets"
    url = f"{base_url}/{sheet_id}/values/{sheet_name or 'Sheet1'}"
    
    with httpx.Client() as client:
        response = client.get(
            url,
            params={"key": api_key},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        
        # Convert to DataFrame
        values = data.get('values', [])
        if not values:
            return pd.DataFrame()
            
        # Use first row as headers
        headers = values[0]
        data_rows = values[1:]
        
        return pd.DataFrame(data_rows, columns=headers) 