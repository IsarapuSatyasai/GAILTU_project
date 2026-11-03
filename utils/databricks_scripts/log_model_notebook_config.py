# Databricks notebook source

# COMMAND ----------

import os

notebook_path = "/Workspace/" + os.path.dirname(
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .notebookPath()
    .get()
)
# MAGIC %cd $notebook_path

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import os  # noqa: E402

notebook_path = "/Workspace/" + os.path.dirname(
    dbutils.notebook.entry_point.getDbutils()
    .notebook()
    .getContext()
    .notebookPath()
    .get()
)
# MAGIC %cd $notebook_path

# COMMAND ----------
ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
workspace_user = ctx.userName().get()

# COMMAND ----------
import sys

sys.path.insert(0, "../../utils/")

# COMMAND ----------
import mlflow  # noqa: E402
from mlflow_helper.log_langchain_model_mlflow import get_args

if "DATABRICKS_RUNTIME_VERSION" in os.environ:
    print("run in dbr notebook.")
    dev_mode = dbutils.widgets.get("environment") == "personal"
    validation_data_path, model_name, environment = get_args(dbutils)

    catalog_type = dbutils.widgets.get("catalog_type")
    ci_code = dbutils.widgets.get("ci_code")
    schema_name = dbutils.widgets.get("schema_name")

    mlflow.set_registry_uri("databricks-uc")

    catalog_name = f"{catalog_type}_{ci_code}_{environment}"

    if dev_mode:
        schema_name = (
            f"dev_{workspace_user.split('@')[0].replace('.', '_')}_" + schema_name
        )

    os.environ["MODEL_NAME"] = model_name
    os.environ["CATALOG_NAME"] = catalog_name
    os.environ["SCHEMA_NAME"] = schema_name

experiment_name = dbutils.widgets.get("experiment_name")
mlflow.set_experiment(experiment_name)
