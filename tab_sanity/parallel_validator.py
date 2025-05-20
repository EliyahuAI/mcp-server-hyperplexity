"""Parallel processing version of the validator."""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time

from .schema_validator import SchemaValidator
from .config import Config, ValidationTarget, ColumnImportance

class ParallelValidator(SchemaValidator):
    """A validator that processes rows in parallel for improved performance."""
    
    def __init__(self, config: Config, api_key: str, enable_next_check_date: bool = True, max_concurrent_rows: int = 5):
        """Initialize the parallel validator.
        
        Args:
            config: The validation configuration
            api_key: Perplexity API key
            enable_next_check_date: Whether to calculate next check dates
            max_concurrent_rows: Maximum number of rows to process in parallel
        """
        super().__init__(config, api_key, enable_next_check_date)
        self.max_concurrent_rows = max_concurrent_rows
        logging.info(f"Initialized ParallelValidator with max {max_concurrent_rows} concurrent rows")
        
    async def validate_dataframe(self, df: pd.DataFrame):
        """Validate all target columns in the DataFrame with parallel processing."""
        # Verify that the primary key columns exist in the DataFrame
        missing_columns = [col for col in self.config.primary_key if col not in df.columns]
        if missing_columns:
            logging.error(f"Primary key columns missing in dataset: {missing_columns}")
            # Use index as fallback if primary key columns are missing
            logging.warning(f"Using row indices as fallback primary key")
            row_key_fn = lambda row, idx: f"Row_{idx}"
        else:
            # Use the configured primary key
            row_key_fn = lambda row, idx: "|".join(str(row[col]) for col in self.config.primary_key)
        
        # Add Last Check and Next Check Date columns if they don't exist
        if "Last Check" not in df.columns:
            df["Last Check"] = pd.NaT  # Use NaT (Not a Time) for empty datetime
        if "Next Check Date" not in df.columns:
            df["Next Check Date"] = pd.NaT

        # Track validation metrics
        start_time = time.time()
        results = {}
        run_log = {
            "total_rows": len(df),
            "multiplex_groups": 0,
            "individual_validations": 0,
            "low_confidence_critical": [],
            "next_check_dates": [],
            "parallel_batches": 0
        }
        
        logging.info(f"Starting parallel validation of {len(df)} rows with max {self.max_concurrent_rows} concurrent rows")
        
        # Process rows in batches to control concurrency
        rows_to_process = list(range(len(df)))
        batches = [rows_to_process[i:i + self.max_concurrent_rows] for i in range(0, len(rows_to_process), self.max_concurrent_rows)]
        
        for batch_idx, batch in enumerate(batches):
            run_log["parallel_batches"] += 1
            logging.info(f"Processing batch {batch_idx+1}/{len(batches)} with {len(batch)} rows")
            
            # Create tasks for each row in the batch
            tasks = []
            for idx in batch:
                row = df.iloc[idx]
                row_key = row_key_fn(row, idx)
                tasks.append(self._process_row(row, row_key, idx))
            
            # Run all tasks in parallel and gather results
            batch_results = await asyncio.gather(*tasks)
            
            # Process batch results
            for idx, (row_key, row_results, mplex_groups, indiv_validations, next_check_date, next_check_reason) in enumerate(batch_results):
                results[row_key] = row_results
                run_log["multiplex_groups"] += mplex_groups
                run_log["individual_validations"] += indiv_validations
                
                # Update the row in the dataframe with check dates
                row_idx = batch[idx]
                df.at[row_idx, "Last Check"] = datetime.now()
                
                if next_check_date:
                    df.at[row_idx, "Next Check Date"] = next_check_date
                    run_log["next_check_dates"].append(next_check_date)
                    results[row_key]["Next Check Date"] = (next_check_date, 1.0, next_check_reason, "HIGH")
                
                # Check for critical items with low confidence
                for target in self.config.validation_targets:
                    if (target.importance == ColumnImportance.CRITICAL and 
                        target.column in row_results and 
                        row_results[target.column][1] < 0.8):  # Use default threshold of 0.8
                        run_log["low_confidence_critical"].append({
                            "row": row_key,
                            "column": target.column,
                            "confidence": row_results[target.column][1],
                            "value": row_results[target.column][0]
                        })
        
        # Log summary
        total_time = time.time() - start_time
        avg_time_per_row = total_time / len(df) if len(df) > 0 else 0
        logging.info(f"Parallel validation completed in {total_time:.2f} seconds")
        logging.info(f"Average time per row: {avg_time_per_row:.2f} seconds")
        logging.info(f"Processed in {run_log['parallel_batches']} parallel batches")
        
        # Generate run summary
        self._log_run_summary(run_log)
        
        return results, df
    
    async def _process_row(self, row: pd.Series, row_key: str, row_idx: int) -> Tuple[str, Dict, int, int, Optional[datetime], List[str]]:
        """Process a single row and return its results."""
        logging.info(f"Starting validation for row {row_idx}: {row_key}")
        
        # Use multiplex validation for this row
        try:
            row_results, mplex_groups, indiv_validations = await self.validate_row_multiplex(row, self.config.validation_targets)
            
            # Calculate next check date if enabled
            next_check_date = None
            next_check_reason = []
            if self.enable_next_check_date:
                try:
                    next_check_date, next_check_reason = await self.determine_next_check_date(row, row_results)
                except Exception as e:
                    logging.error(f"Failed to determine next check date for row {row_key}: {e}")
                    next_check_date = datetime.now() + pd.Timedelta(days=90)
                    next_check_reason = [f"Error calculating: {str(e)}"]
            
            logging.info(f"Completed validation for row {row_idx}: {row_key}")
            return row_key, row_results, mplex_groups, indiv_validations, next_check_date, next_check_reason
            
        except Exception as e:
            logging.error(f"Error processing row {row_key}: {e}")
            return row_key, {}, 0, 0, None, [f"Error: {str(e)}"] 