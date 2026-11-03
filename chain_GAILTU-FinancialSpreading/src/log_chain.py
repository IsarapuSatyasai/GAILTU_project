# Databricks notebook source
# MAGIC %md
# MAGIC ### Instructions
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

# DBTITLE 1,Model path
# Path to the LangGraph entry-point file.
# MLflow will load this file and call set_model() to discover the compiled graph.
lc_model_path = "core/graph/graph_workflow.py"

# COMMAND ----------

# DBTITLE 1,Input example and signature
# --- Input example (matches FinancialGraphState input fields) ---
input_example = {

    "excel_path": "abfss://projects@mscstagailtuprd03.dfs.core.windows.net/FinancialSpreading/Test/creditlens_template_for_ai_model.xlsx", 
    "pdf_source": "projects/FinancialSpreading/InputData/NL/Adyen/Adyenreport.pdf", 
    "output_path": "abfss://projects@mscstagailtuprd03.dfs.core.windows.net/FinancialSpreading/OutputData/NL/Adyen/Adyenreport.xlsx", 
    "pdf_file_name": "/NL/Adyen/Adyenreport.pdf",
}

input_schema = Schema(
    [
        ColSpec("string", "excel_path"),
        ColSpec("string", "pdf_source"),
        ColSpec("string", "output_path"),
        ColSpec("string", "pdf_file_name"),
    ]
)
output_schema = Schema([ColSpec("string")])
signature = ModelSignature(inputs=input_schema, outputs=output_schema)

# COMMAND ----------

# DBTITLE 1,Validation data placeholder
# TODO validation_data is needed for log_chain(), but this functionality isn't used.
validation_data = pd.DataFrame()

# COMMAND ----------

# DBTITLE 1,Code paths for LangGraph dependencies
# All project source files that MLflow needs to bundle alongside the graph entry point.
scripts_path = [
    "core/graph/",
    "core/nodes/",
    "core/prompts/",
    "core/template/",
    "core/models.py",
    "core/config.py",
    "../../utils/custom_lcel_components/",
]
conda_env_path = "../../utils/environment.yml"

# COMMAND ----------

# DBTITLE 1,Log model and register in UC
model_uri, model_version = log_chain(
    lc_model_path,
    input_example,
    validation_data,
    scripts_path=scripts_path,
    conda_env_path=conda_env_path,
    signature=signature,
)

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
    # session_number = model_uri.split("/")[1]
    # print("../mlruns/0/models/" + session_number + "/artifacts/")
