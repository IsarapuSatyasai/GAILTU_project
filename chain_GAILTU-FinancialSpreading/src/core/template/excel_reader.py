"""
This imports and excel file and converts them into spark dataframes
"""

import pandas as pd
from databricks.sdk.runtime import dbutils
import openpyxl
import os
import re
import tempfile

def _sanitize_name(name: str, default: str = "Sheet") -> str:
    """
    Sanitizes a worksheet name to make it compatible to unity catalog table name.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", str(name)).strip("_")
    if not sanitized:
        sanitized = default
    if sanitized[0].isdigit():
        sanitized = "sheet_" + sanitized
    return sanitized


def _sanitize_columns(pd_df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes the column names of a DataFrame to make them compatible with Unity Catalog column names.
    """
    
    seen: dict[str, int] = {}
    new_columns: list[str] = []

    for col in pd_df.columns:
        key = _sanitize_name(col, default="column")
        
        if key in seen:
            seen[key] += 1
            key = f"{key}_{seen[key]}"
        else:
            seen[key] = 1

        new_columns.append(key)
    return pd_df.rename(columns=dict(zip(pd_df.columns, new_columns)))


def read_xlsx(file_path: str) -> dict[str, pd.DataFrame]:
    """
    This function reads an Excel file and returns a dictionary of DataFrames, where each DataFrame corresponds to a worksheet in the Excel file.

    Parameters:
    file_path (str): The path to the Excel file. Supports:
        - abfss:// paths (e.g. "abfss://projects@account.dfs.core.windows.net/.../file.xlsx")
        - /dbfs/mnt paths (legacy, e.g. "/dbfs/mnt/projects/.../file.xlsx")

    Returns:
    A dictionary where the keys are the sanitized worksheet names and the values are the DataFrames.
    """

    if file_path.startswith("abfss://"):
        # Copy from ADLS Gen2 to local temp, then read with pandas
        file_name = os.path.basename(file_path)
        with tempfile.TemporaryDirectory(prefix="fin_spreading_") as temp_dir:
            local_path = os.path.join(temp_dir, file_name)
            dbutils.fs.cp(file_path, f"file://{local_path}")
            pd_worksheets = pd.read_excel(local_path, sheet_name=None, engine="openpyxl")
    else:
        # Legacy /dbfs local path
        dbfs_path = file_path.replace("/dbfs", "dbfs:")
        try:
            dbutils.fs.ls(dbfs_path)
        except:
            raise Exception(f"File not found: {dbfs_path}")
        pd_worksheets = pd.read_excel(file_path, sheet_name=None, engine="openpyxl")

    pandas_dfs = {}
    for worksheet_name, pd_df in pd_worksheets.items():
        # Sanitize the worksheet name
        sanitized_worksheet_name = _sanitize_name(worksheet_name)      
        pd_df = _sanitize_columns(pd_df)
        pandas_dfs[sanitized_worksheet_name] = pd_df

    return pandas_dfs
