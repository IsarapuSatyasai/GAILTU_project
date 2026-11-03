# Databricks notebook source
# MAGIC %md
# MAGIC ## Load traces

# COMMAND ----------

environment = "acc"
volume_path = f"/Volumes/public_gaiep_{environment}/gailtu-annualreport-{environment}/gailtu-annualreport-{environment}_trace"
trace_id= "tr-0e5d10f1021f407b623d2b2a17ed5508"

# COMMAND ----------

import tempfile
import json

file_path = [i for i in dbutils.fs.ls(volume_path) if i.name==trace_id + ".json"]

with tempfile.TemporaryDirectory() as tmpdir:
    local_path = f"{tmpdir}/{trace_id}.json"
    dbutils.fs.cp(
        file_path[0].path,
        f"file://{local_path}"
    )
    with open(local_path, "r", encoding="utf-8") as f:
        trace_json = json.load(f)
