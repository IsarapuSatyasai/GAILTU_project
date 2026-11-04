# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# dependencies = [
#   "-r ../utils/requirements.txt",
#   "openpyxl",
# ]
# ///
# MAGIC %pip install -r ../utils/requirements.txt

# COMMAND ----------

# MAGIC %run ../utils/databricks_scripts/storage_operations

# COMMAND ----------

# MAGIC %pip install --upgrade "openpyxl>=3.1.5"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %load_ext autoreload
# MAGIC # Enable autoreload
# MAGIC %autoreload 2
# MAGIC # disable autoreload
# MAGIC # run %autoreload 0

# COMMAND ----------


STORAGE_ACCOUNT_NAME = "mscstagailtuprd03"
FOLDER_NAME = "projects"
TENANT_ID = "07751f8b-9617-49d5-9024-85f034f400ec"
DBR_MI = "fa515616-7575-408d-8196-320484b017c7"

storage_host = f"{STORAGE_ACCOUNT_NAME}.dfs.core.windows.net"

folder = 'FinancialSpreading'
# List files directly — no mount required
path = f"abfss://{FOLDER_NAME}@{storage_host}/{folder}"
dbutils.fs.ls(path)

# COMMAND ----------

import sys
import os
from datetime import datetime
import logging
import pandas as pd


"""Add path for python dependencies"""
sys.path.insert(0, "../utils")
sys.path.insert(0, "../chain_GAILTU-FinancialSpreading/src/core")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

# COMMAND ----------


# import mlflow
# mlflow.tracing.disable()

# COMMAND ----------

from config import get_settings

# COMMAND ----------

for item in get_settings().paths:
    globals()[item['name']] = item['reference']
    print(item['name']," = ", item['reference'])

# COMMAND ----------

dbutils.widgets.text("mnt", "/mnt/projects/FinancialSpreading/", "Mount path")
dbutils.widgets.text("template_path", "Test/creditlens_template_for_ai_model.xlsx", "Excel template file path")
dbutils.widgets.text("pdf_file_name", "/NL/Adyen/Adyenreport.pdf", "PDF file name")

# COMMAND ----------

mnt = dbutils.widgets.get("mnt")
template_path = dbutils.widgets.get("template_path")
pdf_file_name = dbutils.widgets.get("pdf_file_name")

# file_path = "/dbfs" + mnt + template_path
# xlsx template via abfss:// (variables from cell 6)
file_path = f"abfss://{FOLDER_NAME}@{storage_host}/{folder}/{template_path}"
# PDF source stays on /mnt/ for ingest_documents compatibility
pdf_source = input_path.removeprefix("/mnt/")+ pdf_file_name
# Output path is now abfss:// from config
# output_excel = "dbfs:" + output_path + pdf_file_name.removeprefix("InputData").removesuffix(".pdf") + ".xlsx"
output_excel = output_path + pdf_file_name.removeprefix("InputData").removesuffix(".pdf") + "multi_year_extract.xlsx"

# COMMAND ----------

pdf_source

# COMMAND ----------

file_path

# COMMAND ----------

# temporarily set the environment variable
os.environ["AZURE_OPENAI_API_KEY"] = dbutils.secrets.get(scope="azure-key-vault-scope", key="openai-apim-api-key")

# COMMAND ----------

from graph.graph_workflow import build_graph

graph = build_graph()
print("LangGraph compiled successfully!")

# COMMAND ----------

#PDF source needs to be in this format 'projects/FinancialSpreading/*.pdf'. This is required by ingest document function.

result = graph.invoke(
    {"excel_path": file_path, "pdf_source": pdf_source, "output_path": output_path, "pdf_file_name": pdf_file_name}
)

# COMMAND ----------

result

# COMMAND ----------

for k in result:
    print(k)

# COMMAND ----------

len(result['pdf_pages'])

# COMMAND ----------

result.get('source_language')

# COMMAND ----------

len(result['selected_pages'])

# COMMAND ----------

# Verify output Excel was written to Azure storage (abfss://)
_pdf = result.get('pdf_file_name', '')
_out = result.get('output_path', '')
_expected = _out + _pdf.removeprefix("InputData").removesuffix(".pdf") + ".xlsx"
print(f"Output path: {_expected}")
try:
    info = dbutils.fs.ls(_expected)
    print(f"SUCCESS: {info[0].name}, {info[0].size} bytes")
except Exception as e:
    print(f"NOT FOUND: {e}")

# COMMAND ----------

import re
import json

def to_camel_case(name: str) -> str:
    """Convert a variable name like 'Operational Provisions - cash' to camelCase."""
    # Replace hyphens and special chars with spaces, then split
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', name)
    words = cleaned.split()
    if not words:
        return ''
    # First word lowercase, rest title-cased
    return words[0].lower() + ''.join(w.capitalize() for w in words[1:])

def convert_answer(answer: str):
    """Convert answer string to a numeric value; N/A becomes 0."""
    if answer.strip().upper() == 'N/A':
        return 0
    try:
        return float(answer.replace(',', ''))
    except ValueError:
        return answer

# COMMAND ----------


# Convert entire list of answers to a single camelCase JSON object
result_json = {
    to_camel_case(item['variable']): convert_answer(str(item['answer']))
    for item in result['answers']
}
print(json.dumps(result_json, indent=2))

# COMMAND ----------

print("original answers:")
print(result.get("original_answers"))

print("\nrefined answers:")
print(result.get("refined_answers"))

# COMMAND ----------

print("Years:", result.get("years"))
print("Answers count:", len(result.get("answers", [])))
print("Errors:", result.get("errors"))
print("use_rag:", result.get("use_rag"))
print("rag_collection_name:", result.get("rag_collection_name"))
print("selected_pages:", len(result.get("selected_pages", [])))