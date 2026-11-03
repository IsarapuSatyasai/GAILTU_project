# Databricks notebook source
# MAGIC %pip install -r ../utils/requirements.txt

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %run ../utils/databricks_scripts/storage_operations

# COMMAND ----------

import os
import sys

"""Add path for python dependencies"""
sys.path.insert(0, "../utils")
sys.path.insert(0, "../chain_GAILTU-Sales/src/core")

"""Change this if you are working on dev/acc"""
os.environ["ENVIRONMENT"] = "prd"

# COMMAND ----------

"""Change this if you are working on dev/acc"""
os.environ["OPENAI_API_KEY"] = dbutils.secrets.get(
     scope="azure-key-vault-scope", key="openai-apim-api-key"
 )
os.environ["AZURE_OAI_ENDPOINT"] = "https://msc-apim-gailtu-prd.azure-api.net/openai-api"
os.environ["STORAGE_ACCOUNT"] = "mscstagailtuprd03"
os.environ["SA_ACCESSKEY"] = dbutils.secrets.get(
    scope="azure-key-vault-scope", key="sta-eu-accesskey"
)

# COMMAND ----------

# DBTITLE 1,only used in the notebook

def get_files_from_folder(folder_path: str) -> list:
    """
    Given a folder path in DBFS (Databricks File System), return a list of file paths.

    Args:
        folder_path (str): The folder path relative to /mnt (e.g., "projects/LTU/Sales/Testing/Lukotrans Trucking BV").

    Returns:
        list: A list of full file paths under the given folder.
    """
    # Ensure folder path does not start with '/mnt/' because we add it explicitly
    normalized_folder = folder_path.lstrip('/')

    # List files in the folder using dbutils.fs.ls
    try:
        files = dbutils.fs.ls(f'/mnt/{normalized_folder}')
    except Exception as e:
        raise ValueError(f"Failed to list files in folder '{folder_path}': {e}")

    # Filter only files and build full paths
    file_names = [f.name for f in files if f.isFile()]
    file_locations = [os.path.join(normalized_folder, file_name) for file_name in file_names]

    return file_locations


# COMMAND ----------

from sales_chain import get_sales_chain
from sales_prompts import (
    apt_quote_prompts_dict,
    sales_prompts_dict,
)
from sales_template import (
    sales_template_dict,
)
mlflow.langchain.autolog()

sales_final_chain, sales_chain = get_sales_chain(apt_quote_prompts_dict, sales_prompts_dict, sales_template_dict)

# COMMAND ----------

file_location = get_files_from_folder("projects/LTU/Sales/Testing/DISTRICENTER")

input_dict = {
    "source_list": f"{file_location}",
    "apt_quote_source": "",
    "generated_report_language": "English",
    "credit_vs_oneoff": "", # Use the input from Microsoft form Q3
    "standard_or_nonstandard": "", # Use the input from Microsoft form Q4
    "reason_nonstandard": "", # Use the input from Microsoft form Q5
    "replacement_or_expansion": "", # Use the input from Microsoft form Q6
    "investment_reason": "",# Use the input from Microsoft form Q7
    "company_profile": "", # Use the input from Microsoft form Q8
    "customer_relationship_duration": "", # Use the input from Microsoft form Q9
    "business_volume": "", # Use the input from Microsoft form Q10
    "payment_behavior": "", # Use the input from Microsoft form Q11
    "credit_enhancements": "", # Use the input from Microsoft form Q12
    "recommendation_summary": "", # Use the input from Microsoft form Q13
}

# COMMAND ----------

sales_result = sales_final_chain.invoke(
    input_dict
)

# COMMAND ----------

write_string_to_doc_file(sales_result['final_response_doc'], f"projects/LTU/Sales/Testing/DISTRICENTER/DISTRICENTER - GenAI response sales report.docx")

# COMMAND ----------

#This function can be used to reset the vector db, the collection name can be found as warning of the chain invoke script
from custom_lcel_components.indexing import (
    reset_chroma_db,
)

# reset_chroma_db("TestingLukotransTruckingBV)

# COMMAND ----------

# MAGIC %md ##Investigate individual question
# MAGIC The following code can be used to explore a specific question. For instance, if we want to fine-tune a single prompt, we only need the rag_chain and there's no need to use the annual_report_final_chain, which includes additional steps.

# COMMAND ----------

# DBTITLE 1,investigate individual result
# file_location = "projects/Sales/SuSa STÖTZEL GmbH/inputs/"

question = """Identify the client associated with DLL in the specified transaction. Provide the client’s full company name and complete address as recorded in the transaction details."""

sales_individual_result = sales_chain.invoke(
    {
        "question": question,#business_profile_questions[0],#questions[0],
        "source":  file_location,
        "generated_report_language": "English",
    }
)

# COMMAND ----------

print(sales_individual_result['response']['message'])
