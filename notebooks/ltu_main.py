# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
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
sys.path.insert(0, "../chain_GAILTU-Credit/src/core")

"""Change this if you are working on dev/acc"""
os.environ["ENVIRONMENT"] = "prd"

# COMMAND ----------

"""Change this if you are working on dev/acc"""
os.environ["AZURE_OPENAI_API_KEY"] = dbutils.secrets.get(
     scope="azure-key-vault-scope", key="openai-apim-api-key"
 )
os.environ["AZURE_OPENAI_ENDPOINT"] = "https://msc-apim-gailtu-prd.azure-api.net/openai-api"


os.environ["STORAGE_ACCOUNT"] = "mscstagailtuprd03"

# COMMAND ----------

import logging

import mlflow
from ltu_chain import get_ltu_chain

mlflow.langchain.autolog()
mlflow.llama_index.autolog(disable=True)
logging.getLogger("mlflow.tracing.fluent").setLevel(logging.ERROR)


ltu_final_chain = get_ltu_chain()

# COMMAND ----------

with mlflow.tracing.context(session_id=create_session_id(), user="user-456"):
    ltu_final_output = await ltu_final_chain.ainvoke(
            {
                "additional_report_source": "projects/LTU/Agent/Nomios/Nomios AR 2024.pdf",
                "credit_lens_source": "projects/LTU/Agent/Nomios/MCL 2024 NOMIOS SAS.pdf",
                "existing_credit_report": "projects/LTU/enhance with the existing credit report/Nomios/Nomios Revolving Line Increase Request to 30mln - Green Lane decision March 2026 - final.docx",
                "country_name": "Netherlands",
                "product_name": "Loans for Professional Customers",
                "local_product_name": "Financial Lease Pandrecht / Geldlening",
                "generated_report_language": "English",
            }
        )

# COMMAND ----------

# from datetime import datetime
# now = datetime.now()
# formatted = now.strftime("%Y%m%d")  # e.g. 2026-06-19

# write_string_to_doc_file(ltu_final_output['final_response_doc'], f"projects/LTU/Benelux/creditlens reports/response/Aluminium Duffel - Creditlens GenAI response {formatted}.docx")

# COMMAND ----------

#This function can be used to reset the vector db, the collection name can be found as warning of the chain invoke script
from custom_lcel_components.indexing import (
    reset_chroma_db,
)

reset_chroma_db("creditlensreportsMainfreightAnnualReport2024pdf")

# COMMAND ----------

# MAGIC %md
# MAGIC

# COMMAND ----------

# MAGIC %md
# MAGIC ## Store test cases

# COMMAND ----------

#this key and endpoint are for the endpoints with cache, use this to generate test cases only as it is quite expensive to use the cache.
# that you do not have to deal with randomness of the OpenAI endpoint; they output is fixed
from ltu_chain import get_ltu_chain

os.environ["AZURE_OPENAI_ENDPOINT"] = "https://msc-apim-gailtu-prd.azure-api.net/openai-api-redis"
ltu_final_chain = get_ltu_chain()
additional_report_source = ["", "projects/LTU/regression_test/creditlens_reports/Mainfreight-Annual-Report-2024.pdf"]
credit_lens_source = ["projects/LTU/regression_test/creditlens_reports/Bam Wine Logistics Pty Limited CL (SME).pdf", "projects/LTU/regression_test/creditlens_reports/Creditlens Mainfreight.pdf"]

for additional_report, credit_lens in zip(additional_report_source, credit_lens_source):
    inputs = {
            "additional_report_source": additional_report,
            "credit_lens_source": credit_lens,
            "existing_credit_report": "",
            "country_name": "Netherlands",
            "product_name": "Loans for Professional Customers",
            "local_product_name": "Financial Lease Pandrecht / Geldlening",
            "generated_report_language": "English",
        }
    ltu_final_output = await ltu_final_chain.ainvoke(
        inputs
    )
    # store a test case and then commit the test case to the repo.
    store_regression_test_case(inputs, ltu_final_output, filename_keys=["additional_report_source", "credit_lens_source"], trace_name=ltu_final_chain.name)