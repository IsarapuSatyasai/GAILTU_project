# Databricks notebook source
# MAGIC %md
# MAGIC This notebook is used to calculate the metrics which are visualized in the dashboard. The script runs on a weekly basis.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install dependencies

# COMMAND ----------

# MAGIC %pip install mlflow-skinny==3.15.0
# MAGIC %pip install langchain-openai==1.3.2
# MAGIC %pip install llama-index-embeddings-azure-openai==0.5.2


# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Settings

# COMMAND ----------

# define location of table in UC, either read from widgets in a job and acc otherwise
import os

import mlflow

try:
    ENVIRONMENT = dbutils.widgets.get("environment_full_name")
except Exception as e:
    print("Local run: " + str(e))
    ENVIRONMENT = "prd"

try:
    CI_CODE = dbutils.widgets.get("ci_code")
except Exception as e:
    print("Local run: " + str(e))
    CI_CODE = "gailtu"

os.environ["CI_CODE"] = CI_CODE
os.environ["ENVIRONMENT"] = ENVIRONMENT

ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
workspace_user = ctx.userName().get()

try:
    dev_mode = dbutils.widgets.get("environment") == "personal"
except Exception as e:
    print("Local run: " + str(e))
    dev_mode = False

try:
    catalog_type = dbutils.widgets.get("catalog_type")
    catalog_name = f"{catalog_type}_{CI_CODE}_" + dbutils.widgets.get(
        "environment_full_name"
    )
    schema_name = dbutils.widgets.get("schema_name")
    sql_warehouse_id = dbutils.widgets.get("sql_warehouse_id")

except Exception as e:
    print("Local run: " + str(e))
    catalog_type = "private"
    catalog_name = f"{catalog_type}_{CI_CODE}_prd"
    schema_name = (
        f"dev_{workspace_user.split('@')[0].replace('.', '_')}_"
        + CI_CODE
        + "-credit-personal"
    )
    sql_warehouse_id = "d94299f7dcf31988"  # Lifecycle production sql warehouse id


if dev_mode:
    schema_name = f"dev_{workspace_user.split('@')[0].replace('.', '_')}_" + schema_name

try:
    time_window = int(dbutils.widgets.get("lookback_window"))
except Exception as e:
    print("Local run: " + str(e))
    time_window = 7
try:
    experiment_name = dbutils.widgets.get("experiment_name")
except Exception as e:
    print("Local run: " + str(e))
    experiment_name = f"/Workspace/Users/{workspace_user}/.bundle/chain_GAILTU-AnnualReport/GAILTU-AnnualReport-personal"


experiment_id = mlflow.get_experiment_by_name(experiment_name).experiment_id

import os

import mlflow

mlflow.set_tracking_uri("databricks")

try:
    client_id = dbutils.widgets.get("client_id")
except Exception as e:
    print("Local run: " + str(e))
    client_id = ""

if client_id != "":
    # Service principal auth: client secret lives in Key Vault, name is env-specific
    client_secret_key = "MSC-APP-GAIEP-{env}-GAILTU".format(
        env=os.environ["ENVIRONMENT"].upper()
    )
    os.environ["AZURE_CLIENT_ID_JOB"] = client_id
    os.environ["AZURE_TENANT_ID_JOB"] = dbutils.widgets.get("tenant_id")
    os.environ["AZURE_CLIENT_SECRET_JOB"] = dbutils.secrets.get(
        scope="azure-key-vault-scope", key=client_secret_key
    )
    os.environ["AZURE_OPENAI_ENDPOINT"] = (
        "https://msc-apim-{ci_code}-{env}.azure-api.net".format(
            ci_code=os.environ["CI_CODE"], env=os.environ["ENVIRONMENT"]
        )
    )
else:
    os.environ["AZURE_OPENAI_API_KEY"] = dbutils.secrets.get(
        scope="azure-key-vault-scope", key="openai-apim-api-key"
    )
    os.environ["AZURE_OPENAI_ENDPOINT"] = (
        "https://msc-apim-{ci_code}-{env}.azure-api.net/openai-api".format(
            ci_code=os.environ["CI_CODE"], env=os.environ["ENVIRONMENT"]
        )
    )


os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = sql_warehouse_id

# COMMAND ----------
import datetime

timestamp = str(
    int(
        (datetime.datetime.now() - datetime.timedelta(days=time_window)).timestamp()
        * 1000
    )
)
print(catalog_name, schema_name, experiment_id)

traces = mlflow.search_traces(
    locations=[f"{catalog_name.lower()}.{schema_name.lower()}.{experiment_id}"],
    filter_string=f"trace.name ILIKE '%completions%' AND trace.timestamp_ms > '{timestamp}'",
    order_by=["timestamp_ms DESC"],
)
print(len(traces))


# COMMAND ----------
import sys

sys.path.insert(0, "../utils/metrics")
sys.path.insert(0, "../utils")

from llm_evaluation import hallucination, numerical_inaccuracy

results = mlflow.genai.evaluate(
    data=traces,
    scorers=[numerical_inaccuracy, hallucination],
)
