# Databricks notebook source
# MAGIC %md
# MAGIC ### Batch predictions

# COMMAND ----------

# MAGIC %md
# MAGIC ### Instructions
# MAGIC
# MAGIC When you want to run this notebook directly, outside of the Databricks Asset Bundle (DAB), you need to specify the input widgets. These input widgets are set at runtime when deploying the DAB, so when running this notebook outside the bundle the widgets can't be found.
# MAGIC
# MAGIC Ensure to remove these widgets when you want to deploy.
# MAGIC
# MAGIC The widgets can be set as follows: `dbutils.widgets.text("environment", "personal")`
# MAGIC
# MAGIC All widgets needed are:
# MAGIC - `model_name`
# MAGIC - `experiment_name`
# MAGIC - `input`
# MAGIC - `environment`
# MAGIC - `output_path`
# MAGIC
# MAGIC _Note these widgets need to be set after restarting the Python Interperter_

# COMMAND ----------

# MAGIC %pip install databricks-cli

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

"""Set widgets if not exist"""


ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
workspace_user = ctx.userName().get()

if not dbutils.widgets.getAll():
    dbutils.widgets.text("environment", "personal")
    dbutils.widgets.text("model_name", "LTU-Annual-Report")
    dbutils.widgets.text(
        "experiment_name", f"/Workspace/Users/{workspace_user}/-LTU-Annual-Report"
    )
    dbutils.widgets.text(
        "input",
        '{"source": "projects/LTU/Benelux/annual_reports/KLM-Annual-Report_2023.pdf", "storage_account": "mscstagailtudev03", "country_name": "Netherlands", "product_name": "Loans for Professional Customers", "local_product_name": "Financial Lease Pandrecht / Geldlening"}',
    )
    dbutils.widgets.text("output_path", "large-ticket-underwriting/output_example.html")
    dbutils.widgets.text("sql_warehouse_id", "")

# COMMAND ----------

import os

os.environ["ENVIRONMENT"] = dbutils.widgets.get("environment_full_name")
os.environ["CI_CODE"] = dbutils.widgets.get("ci_code")

# This field always need to be present in the validation data, the others can depend on the model
AZURE_KEY_VAULT_SCOPE = "azure-key-vault-scope"
AZURE_OPENAI_ACCESS_KEY = "openai-apim-api-key"
AZURE_STORAGE_ACCESS_KEY = "sta-eu-accesskey"


# COMMAND ----------

"""Import packages and secrets"""

import json
import logging

import mlflow
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from mlflow.entities.trace_location import UnityCatalog

logging.getLogger("mlflow.tracing.fluent").setLevel(logging.ERROR)
logging.getLogger("mlflow.entities").setLevel(logging.ERROR)
logging.getLogger("mlflow.store").setLevel(logging.ERROR)

# MLflow 3.15 performance optimization: disable autolog during model loading
mlflow.llama_index.autolog(disable=True)
# mlflow.langchain.autolog() - will be re-enabled after model load

mlflow.set_registry_uri("databricks-uc")

"""Set experiment, get Secrets and widgets"""
experiment_name = dbutils.widgets.get("experiment_name")
mlflow.set_tracking_uri("databricks")

"""Set api keys as env variables"""
client_id = dbutils.widgets.get("client_id")

if client_id != "":
    # Service principal auth: client secret lives in Key Vault, name is env-specific
    client_secret_key = "MSC-APP-GAIEP-{env}-GAILTU".format(
        env=os.environ["ENVIRONMENT"].upper()
    )
    os.environ["AZURE_CLIENT_ID_JOB"] = client_id
    os.environ["AZURE_TENANT_ID_JOB"] = dbutils.widgets.get("tenant_id")
    os.environ["AZURE_CLIENT_SECRET_JOB"] = dbutils.secrets.get(
        scope=AZURE_KEY_VAULT_SCOPE, key=client_secret_key
    )
    os.environ["AZURE_OPENAI_ENDPOINT"] = (
        "https://msc-apim-{ci_code}-{env}.azure-api.net".format(
            ci_code=os.environ["CI_CODE"], env=os.environ["ENVIRONMENT"]
        )
    )
else:
    os.environ["AZURE_OPENAI_API_KEY"] = dbutils.secrets.get(
        scope=AZURE_KEY_VAULT_SCOPE, key=AZURE_OPENAI_ACCESS_KEY
    )
    os.environ["AZURE_OPENAI_ENDPOINT"] = (
        "https://msc-apim-{ci_code}-{env}.azure-api.net/openai-api".format(
            ci_code=os.environ["CI_CODE"], env=os.environ["ENVIRONMENT"]
        )
    )


os.environ["STORAGE_ACCOUNT"] = "mscsta{ci_code}{env}".format(
    ci_code=os.environ["CI_CODE"], env=os.environ["ENVIRONMENT"]
)

# COMMAND ----------

"""Set widgets"""

model_name = dbutils.widgets.get("model_name")
output_path = dbutils.widgets.get("output_path")
sql_warehouse_id = dbutils.widgets.get("sql_warehouse_id")

dev_mode = dbutils.widgets.get("environment") == "personal"

catalog_type = dbutils.widgets.get("catalog_type")
catalog_name = f"{catalog_type}_{os.environ['CI_CODE']}_{os.environ['ENVIRONMENT']}"
schema_name = dbutils.widgets.get("schema_name")
if dev_mode:
    schema_name = f"dev_{workspace_user.split('@')[0].replace('.', '_')}_" + schema_name
schema_name = schema_name.lower()


"""Configure Unity Catalog trace storage"""
os.environ["MLFLOW_TRACING_SQL_WAREHOUSE_ID"] = sql_warehouse_id

# mlflow.set_experiment is an upsert operation
experiment = mlflow.set_experiment(
    experiment_name=experiment_name,
    trace_location=UnityCatalog(
        catalog_name=catalog_name,
        schema_name=schema_name,
        # table_prefix=model_name,  # defaults to experiment id if not provided
    ),
)

# COMMAND ----------

"""Get input and load models from registry"""

"""Load models from registry"""
input = json.loads(dbutils.widgets.get("input"))
model_uri = f"models:/{catalog_name}.{schema_name}.{model_name}@champion"
# Load model with autolog disabled for MLflow 3.15 performance
model_chain = mlflow.langchain.load_model(model_uri)
model_chain.name = model_name
# Re-enable autolog for inference tracing
mlflow.langchain.autolog()

# COMMAND ----------

import uuid
from datetime import datetime, timezone


def create_session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    unique_part = uuid.uuid4().hex[:8]
    return f"{timestamp}_{unique_part}"


"""Generate responses from the target model and store result in blob storage"""
with mlflow.tracing.context(session_id=create_session_id(), user="user-456"):
    response = await model_chain.ainvoke(input)
    mlflow.set_tag("input", input)

# COMMAND ----------

"""Store outputs in blob storage"""
if "spreading" in schema_name.lower():
    pass
else:  
    if ".html" in output_path:
        output_path = output_path.replace(".html", ".docx")
    local_path = "/tmp/my_document.docx"
    response.save(local_path)


    blob_service_client = BlobServiceClient(
        account_url="https://" + os.environ["STORAGE_ACCOUNT"] + ".blob.core.windows.net/",
        credential=DefaultAzureCredential(),
    )
    parts = output_path.lstrip("/").split("/", 1)
    container_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""
    blob_client = blob_service_client.get_blob_client(
        container=container_name, blob=blob_name
    )

    print(output_path, blob_name, container_name)

    with open(local_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)
