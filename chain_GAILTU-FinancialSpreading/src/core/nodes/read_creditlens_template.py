"""
Read Credit lens template that is saved in an excel file.
Each excel worksheet contains a table containing metric and definition as per RaboDet template guide.
This function reads these tables.
"""

import pandas as pd

from graph.graph_state import FinancialGraphState
from template.excel_reader import read_xlsx

def read_creditlens_template(state: FinancialGraphState) -> dict:
    """
    Read Credit lens template that is saved in an excel file.
    Each excel worksheet contains a table containing metric and definition as per RaboDet template guide. 
    return read_xlsx(state["excel_path"])
    """

    excel_path = state["excel_path"]
    creditlens_metrics = []

    try:        
        creditlens_dfs = read_xlsx(excel_path)

        for worksheet_name, pd_df in creditlens_dfs.items():
            # pd_df = pd_df.where(pd_df.notnull(pd_df), None)

            for _, row in pd_df.iterrows():
                row_id = row["No"]
                variable = row["Variable"]
                description = row["Description"]
                formula = row["Formula"]
                remarks = row["Remarks"]
                # priority = row["Priority"]

                if variable and variable not in ["table_name", "table_description"]:
                    creditlens_metrics.append(
                        {
                            "worksheet": worksheet_name,
                            "row_id" : row_id,
                            "variable": variable,
                            "description": description if pd.notna(description) else None,
                            "formula": formula if pd.notna(formula) else None,
                            # "priority": priority if pd.notna(priority) else "Medium",
                            "remarks": remarks if pd.notna(remarks) else None
                        }
                    )
            
        return {"excel_data": creditlens_metrics, "errors": []}

    except Exception as e:
        return {"excel_data": {}, "errors": [f"Excel read error: {str(e)}"]}
