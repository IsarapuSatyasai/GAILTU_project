# Databricks notebook source
# MAGIC %md # LTU - Update Red List
# MAGIC ##Purpose of the Notebook
# MAGIC The solution performs an exact company name match to identify whether an entity appears on the Red List. This notebook is used to maintain and update the Red List, using source data provided by Vicario, G. (Gabriele).
# MAGIC
# MAGIC Once the source files are shated, they must be manually downloaded and uploaded to the designated storage account at the specified path. 
# MAGIC - LTU/ESG/RedList/Private Companies Exclusion List (Q1 26).xlsx
# MAGIC - LTU/ESG/RedList/Public Companies Exclusion List (Q1 26).xlsx
# MAGIC
# MAGIC After this step, the notebook should be executed to refresh the Red List with the latest information.

# COMMAND ----------

# MAGIC %run ../utils/databricks_scripts/storage_operations

# COMMAND ----------

private_companies_exclusion_list_Q1_26 = read_excel("projects/LTU/ESG/RedList/Private Companies Exclusion List (Q1 26).xlsx", skiprows=2, sheet_name=None)
public_companies_exclusion_list_Q1_26 = read_excel("projects/LTU/ESG/RedList/Public Companies Exclusion List (Q1 26).xlsx", skiprows=2, sheet_name=None)

# COMMAND ----------

public_companies_exclusion_list_Q1_26['Public Companies Exclusion List'].head()

# COMMAND ----------

private_companies_exclusion_list_Q1_26['Private Companies Exclusion Lis'].head()

# COMMAND ----------

red_list = public_companies_exclusion_list_Q1_26['Public Companies Exclusion List']["Entity Name"].tolist() + private_companies_exclusion_list_Q1_26['Private Companies Exclusion Lis']["Entity Name"].tolist()

# COMMAND ----------

# # Define the output file path
output_file_path = f"../chain_GAILTU-AnnualReport/src/core/red_list.py"

# Ensure the directory exists
os.makedirs(os.path.dirname(output_file_path), exist_ok=True) if os.path.dirname(output_file_path) else None

# Open the output file for writing all dictionaries
with open(output_file_path, "w") as f:
    # Write the list to the file
    f.write(f"red_list = {red_list}")
