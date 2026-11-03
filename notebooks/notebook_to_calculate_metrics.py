# Databricks notebook source
# MAGIC %md
# MAGIC This notebook can be used to read the traces as json in the local environment and calculate the llm evaluation metrics with the existing metrics or develop new metrics

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load traces

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

environment = "acc"
volume_path = f"/Volumes/public_gaiep_{environment}/gailtu-annualreport-{environment}/gailtu-annualreport-{environment}_trace"
# trace_id= "tr-0e5d10f1021f407b623d2b2a17ed5508"  #old trace format
# trace_id= "tr-016c4d22f5e2d71dff96b0f531efdae8"

# trace_id= "tr-1fa9b750cc2647861b20c9a29cb8c55d"
# trace_id = "tr-24f6310d85b76b2cb216901ab9f8b8ea"

# trace_id ="tr-2e2478ed426b33aff39bf5bb13771919"

trace_id ="tr-03d438c09b48ee75b910c5aba0fe5876"

# COMMAND ----------

import sys,os
import json

sys.path.insert(0, "../utils/databricks_scripts")
sys.path.insert(0, "../utils/metrics")

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


from llm_evaluation import (
    
    async_numerical_inaccuracy,
)

from trace_utils import (
    construct_question_response,
    retrieve_step_output_from_trace,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ##Read from Json

# COMMAND ----------




# 1) Locate the exact file in DBFS
target_name = f"{trace_id}.json"

try:
    entries = dbutils.fs.ls(volume_path)
except Exception as e:
    raise RuntimeError(f"Cannot list {volume_path}: {e}")

matches = [fi for fi in entries if fi.name == target_name]
if not matches:
    raise FileNotFoundError(f"No file named '{target_name}' found under: {volume_path}")

# If multiple matches exist, you can choose the first or add tie-breaker logic:
file_info = matches[0]           # <-- this is what you asked for
print("Using file:", file_info.path)

# 2) Read as raw text with Spark and parse (works when local FS is restricted)
df = spark.read.text(file_info.path)
json_str = "".join([r.value for r in df.collect()])  # safe for single JSON object
trace_json = json.loads(json_str)

# (Optional) quick sanity check
print("Top-level keys:", list(trace_json.keys())[:20])

# COMMAND ----------

# MAGIC %md
# MAGIC ##Read input, responses and context from the trace and prepare llm evaluation data

# COMMAND ----------

input = json.loads(trace_json["data"]["spans"][0]["attributes"]["mlflow.spanInputs"])

# COMMAND ----------

responses = retrieve_step_output_from_trace(trace_json, "get_response_gpt", add_input=True, exact_match=True)

# COMMAND ----------

responses.keys()

# COMMAND ----------

responses['get_response_gpt_0'].keys()

# COMMAND ----------

responses['get_response_gpt_0']['input']

# COMMAND ----------

json.loads(responses['get_response_gpt_0']["output"]).keys()

# COMMAND ----------

responses['get_response_gpt_1']['output']

# COMMAND ----------

augment_prompt = retrieve_step_output_from_trace(trace_json, "augment_prompt", add_input=True)

# COMMAND ----------

ingested_documents = retrieve_step_output_from_trace(trace_json, "ingest_documents", add_input=True)

# COMMAND ----------

ingested_documents.keys()

# COMMAND ----------

llm_evaluation_data = construct_question_response(augment_prompt, responses)

# COMMAND ----------

llm_evaluation_data.keys()

# COMMAND ----------

import nest_asyncio

os.environ["OPENAI_API_KEY"] = dbutils.secrets.get(
    scope="azure-key-vault-scope", key="openai-apim-api-key"
)

# COMMAND ----------

len(llm_evaluation_data)

# COMMAND ----------

# MAGIC %md
# MAGIC ##Example of one llm_evaluation metric -  numerical inaccuracy checker

# COMMAND ----------

nest_asyncio.apply()

numerical_inaccuracy = async_numerical_inaccuracy(responses)

# COMMAND ----------

len(numerical_inaccuracy)

# COMMAND ----------

numerical_inaccuracy[0].keys()

# COMMAND ----------

# MAGIC %md
# MAGIC ##Display the results of the metric

# COMMAND ----------

for i in range(0,len(numerical_inaccuracy)):
    print("Question", i, ': ', numerical_inaccuracy[i]['question'],"\n")
    print("Overall rating is ", numerical_inaccuracy[i]['overall_rating_acc'],"\n")
    print("Reasoning is ", numerical_inaccuracy[i]['reasoning_ac'],"\n")
    print("****************************\n")


# COMMAND ----------

# MAGIC %md
# MAGIC
