# Databricks notebook source
# MAGIC %md
# MAGIC ### Insctructions
# MAGIC
# MAGIC When you want to run this notebook directly, outside of the Databricks Asset Bundle (DAB), you need to specify the input widgets. These input widgets are set at runtime when deploying the DAB, so when running this notebook outside the bundle the widgets can't be found.
# MAGIC
# MAGIC Ensure to remove (or comment out) these widgets when you want to deploy.
# MAGIC
# MAGIC The widgets can be set as follows: `dbutils.widgets.text("environment", "personal")`
# MAGIC
# MAGIC All widgets needed are:
# MAGIC - `model_name`
# MAGIC - `experiment_name`
# MAGIC - `input`
# MAGIC - `environment`

# COMMAND ----------

# MAGIC %run ../../utils/databricks_scripts/log_model_notebook_config

# COMMAND ----------

import os
import sys

import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import ModelSignature
from mlflow.types.schema import ColSpec, Schema

sys.path.insert(0, "../../utils/")
sys.path.insert(0, "core/")

# COMMAND ----------

from mlflow_helper.log_langchain_model_mlflow import log_chain

# COMMAND ----------

"""Pipeline steps"""
# these are the inputs for the RAG pipeline

# COMMAND ----------

country_name = "Netherlands"

# Normalize env vars so downstream libraries can consistently read them.
os.environ["AZURE_OPENAI_API_KEY"] = "xxx"
os.environ["AZURE_OPENAI_ENDPOINT"] = "xxx"

lc_model_path = "core/ltu_chain.py"

# COMMAND ----------


creditlens_file_location = "projects/LTU/Benelux/creditlens reports/Creditlens Kuehne + Nagel International AG.pdf"
additional_report_file_location = ""
existing_credit_report_file_location = ""
product_name = "Loans for Professional Customers"
local_product_name = "Financial Lease Pandrecht / Geldlening"
# generated_report_language indicates the language in which the AI-generated report will be produced. If the user selects Dutch as the generated_report_language, the final Word document will be translated accordingly.
generated_report_language = "English"

input_example = {
    "additional_report_source": additional_report_file_location,
    "credit_lens_source": creditlens_file_location,
    "existing_credit_report": existing_credit_report_file_location,
    "country_name": country_name,
    "product_name": product_name,
    "local_product_name": local_product_name,
    "generated_report_language": generated_report_language,
}


input_schema = Schema(
    [
        ColSpec("string", "additional_report_source"),
        ColSpec("string", "credit_lens_source"),
        ColSpec("string", "existing_credit_report"),
        ColSpec("string", "country_name"),
        ColSpec("string", "product_name"),
        ColSpec("string", "local_product_name"),
        ColSpec("string", "generated_report_language"),
    ]
)
output_schema = Schema([ColSpec("string")])
signature = ModelSignature(inputs=input_schema, outputs=output_schema)

# COMMAND ----------

# TODO validation_data is needed for log_chain(), but this functionally isn't used.
validation_data = pd.DataFrame()

# COMMAND ----------

scripts_path = [
    "../../utils/custom_lcel_components/",
    "core/agent_system_prompt.py",
    "core/annual_report_agent_utils.py",
    "core/annual_report_european_prompts.py",
    "core/annual_report_prompts.py",
    "core/annual_report_utils.py",
    "core/create_credit_report_word_template_utils.py",
    "core/Credit-Report-Template-Rabobank.docx",
    "core/financial_analysis_prompts.py",
    "core/financial_analysis_european_prompts.py",
    "core/financial_analysis_utils.py",
    "core/financial_analysis_agent_utils.py",
    "core/financial_product_catalogue_dec.py",
    "core/ltu_chains_utils.py",
    "core/red_list.py",
]
conda_env_path = "../../utils/environment.yml"


model_uri, model_version = log_chain(
    lc_model_path,
    input_example,
    validation_data,
    scripts_path=scripts_path,
    conda_env_path=conda_env_path,
    signature=signature,
)
RUN_DBR = False

if "DATABRICKS_RUNTIME_VERSION" in os.environ:
    RUN_DBR = True

if "DATABRICKS_RUNTIME_VERSION" in os.environ:
    client = MlflowClient()
    catalog_name = os.environ["CATALOG_NAME"]
    schema_name = os.environ["SCHEMA_NAME"]
    model_name = os.environ["MODEL_NAME"]

    model_name = f"{catalog_name}.{schema_name}.{model_name}"
    output = mlflow.register_model(model_uri, model_name)
    client.set_registered_model_alias(model_name, "Champion", output.version)

# COMMAND ----------

if "DATABRICKS_RUNTIME_VERSION" in os.environ:
    dbutils.notebook.exit(model_uri)
else:
    # Print the native MLflow model URI (e.g. models:/<id>) so it resolves via the
    # tracking backend (file store, SQLite, or Databricks) instead of a hardcoded path.
    print(model_uri)
