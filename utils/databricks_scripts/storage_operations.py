# Databricks notebook source
# MAGIC %pip install openpyxl==3.0.10
# MAGIC %pip install pypdf

# COMMAND ----------

import json
import logging
import os
import pickle
import uuid
from datetime import datetime, timezone

import mlflow
import pandas as pd
from mlflow.tracing.provider import trace_disabled
from mlflow.tracking import MlflowClient

NAME_OF_AUGMENTATION_STEP = "augment_prompt"

BASELINE_FOLDER_NAME_AUGMENTATION = "baseline_augmented_prompts"
BASELINE_FOLDER_NAME_RESPONSE = "baseline_response"
logger = logging.getLogger(__name__)

# COMMAND ----------

# Yes! You can list files directly using abfss:// without mounting.
# The spark.conf OAuth settings below allow direct access via the abfss:// protocol.
# No mount point (/mnt/...) is needed — dbutils.fs.ls works directly with abfss:// paths.

STORAGE_ACCOUNT_NAME = "mscstagailtuprd03"
FOLDER_NAME = "projects"
TENANT_ID = "07751f8b-9617-49d5-9024-85f034f400ec"
DBR_MI = "fa515616-7575-408d-8196-320484b017c7"

storage_host = f"{STORAGE_ACCOUNT_NAME}.dfs.core.windows.net"


spark.conf.set(f"fs.azure.account.auth.type.{storage_host}", "OAuth")
spark.conf.set(
    f"fs.azure.account.oauth.provider.type.{storage_host}",
    "org.apache.hadoop.fs.azurebfs.oauth2.MsiTokenProvider",
)
spark.conf.set(
    f"fs.azure.account.oauth2.msi.tenant.{storage_host}",
    TENANT_ID,
)
spark.conf.set(
    f"fs.azure.account.oauth2.client.id.{storage_host}",
    DBR_MI,
)
# See below an example how to access the storage account directly
# folder = 'FinancialSpreading/Test'
# # List files directly — no mount required
# path = f"abfss://{container_name}@{storage_host}/{folder}"
# dbutils.fs.ls(path)

# COMMAND ----------


def read_csv(file_path, **kwargs):
    df = pd.read_csv("/dbfs/mnt/" + file_path, **kwargs)
    return df


# COMMAND ----------


def write_csv(df: pd.DataFrame, file_path, **kwargs):
    df.to_csv("/dbfs/mnt/" + file_path, **kwargs)


# COMMAND ----------


def read_excel(file_path, **kwargs):
    # set default engine to openpyxl
    if "engine" not in kwargs.keys():
        kwargs["engine"] = "openpyxl"
    df = pd.read_excel("/dbfs/mnt/" + file_path, **kwargs)
    return df


# COMMAND ----------


def read_excel_as_dict(file_path, **kwargs):
    excel_df = pd.ExcelFile("/dbfs/mnt/" + file_path, **kwargs)
    dct_df = {}
    for sheet_name in excel_df.sheet_names:
        df_new = excel_df.parse(sheet_name=sheet_name)
        ## populate dictionary
        dct_df[sheet_name] = df_new
    return dct_df


# COMMAND ----------


def read_pickle(file_path, **kwargs):
    df = pd.read_pickle("/dbfs/mnt/" + file_path, **kwargs)
    return df


# COMMAND ----------


def write_pickle(data, file_path, **kwargs):
    with open("/dbfs/mnt/" + file_path, "wb") as f:
        pickle.dump(data, f, **kwargs)


# COMMAND ----------


def read_pdf(file_path, **kwargs):
    from pypdf import PdfReader

    reader = PdfReader("/dbfs/mnt/" + file_path, **kwargs)
    text = [page.extract_text() for page in reader.pages]
    return text


# COMMAND ----------


def write_html(data, file_path, **kwargs):
    with open("/dbfs/mnt/" + file_path, "wb") as f:
        f.write(data.encode("utf-8"))


# COMMAND ----------


def write_string_to_doc_file(doc_string, file_path):
    """
    Saves a given document string to a local file and then moves it to a mounted Blob Storage.

    Parameters:
    path (str): The destination path in the mounted Blob Storage.
    doc_string (Document): The document object to be saved.

    Returns:
    None
    """
    local_path = "/tmp/my_document.docx"
    doc_string.save(local_path)

    # Move the document to the mounted Blob Storage
    dbutils.fs.cp(f"file:{local_path}", "/mnt/" + file_path)


# COMMAND ----------


def get_input_from_trace(trace: dict):
    """
    Extracts the input data from a given trace.

    Args:
        trace (dict): The trace object containing the data.

    Returns:
        dict: A dictionary containing the input data.
    """
    inputs = json.loads(trace["data"]["spans"][0]["attributes"]["mlflow.spanInputs"])
    return inputs


def get_output_from_trace(trace: dict, step_output_name: str):
    """
    Extracts the output data from a given trace for a specific step.

    Args:
        trace (dict): The trace object containing the data.
        step_output_name (str): The name of the step to extract the output from.

    Returns:
        dict: A dictionary containing the output data for the specified step.
    """
    response = json.loads(
        [
            i
            for i in trace["data"]["spans"]
            if f"RunnableAssign<{step_output_name}>" in i["name"]
        ][-1]["attributes"]["mlflow.spanOutputs"]
    )[step_output_name]
    return response


# @trace_disabled
# def get_augmented_prompts_from_trace(trace: dict) -> dict:
#     """
#     Extracts augmented prompts and their corresponding questions from a given trace.

#     Args:
#         trace (Trace): The trace object containing the data.

#     Returns:
#         dict: A dictionary containing the filename, augmented prompts, questions, and the final response.
#     """
#     inputs = get_input_from_trace(trace)
#     augment_spans = [
#         i for i in trace["data"]["spans"] if NAME_OF_AUGMENTATION_STEP in i["name"]
#     ]
#     assert len(augment_spans) > 0
#     augmented_prompts = {}
#     for augment_span in augment_spans:
#         prompt = json.loads(augment_span["attributes"]["mlflow.spanOutputs"])
#         question = json.loads(augment_span["attributes"]["mlflow.spanInputs"])[
#             "question"
#         ]
#         augmented_prompts[augment_span["name"]] = {
#             "prompt": prompt,
#             "question": question,
#         }
#     augmented_prompts["inputs"] = inputs
#     return augmented_prompts

# COMMAND ----------


@trace_disabled
def load_traces(trace_name, n=1):
    """
    Loads the last successful trace from the MLflow experiment associated with the current notebook.

    Returns:
        list: A list of traces.
    """
    notebook_path = (
        dbutils.notebook.entry_point.getDbutils()
        .notebook()
        .getContext()
        .notebookPath()
        .get()
    )
    experiment_id = mlflow.get_experiment_by_name(notebook_path).experiment_id
    client = MlflowClient()
    traces = client.search_traces(
        experiment_ids=[experiment_id],
        filter_string="attributes.status = 'OK'",
        max_results=n,
    )

    return traces


# def store_rag_testcase_from_trace(step_output_name="responses", trace_name="annual_report_chain"):
#     """
#     Stores the last successful trace as a JSON file. The trace is retrieved from the MLflow experiment
#     associated with the current notebook. The JSON file is saved in a predefined directory based on whether
#     augmented prompts are to be stored or not.

#     Args:
#         step_output_name (str): The name of the step that contains the final output (before optional conversion to word document).
#     """
#     # This is to make sure that the cache endpoint is used to store the test case.
#     assert "apim" in os.environ["AZURE_OAI_ENDPOINT"]

#     traces = load_traces(trace_name)
#     augmented_traces = load_traces("RAG_chain_sentence_window", n=20)

#     main_trace = traces[0].to_dict()
#     for i, trace in enumerate(augmented_traces):
#         augment_trace = trace.to_dict()["data"]["spans"]
#         augment_trace["name"] = augment_trace["name"] + "_" + str(i)
#         main_trace["data"]["spans"] += trace.to_dict()["data"]["spans"]


#     traces_dict = get_augmented_prompts_from_trace(main_trace)

#     # Note the final step with step_output_name is taken for the responses, it should be a runnable-assign
#     response = get_output_from_trace(main_trace, step_output_name)
#     traces_dict["response"] = {step_output_name: response}

#     output_file_name = (
#         traces_dict["inputs"]["source"].split("/")[-1].replace(".pdf", ".json")
#     )
#     file_path = os.path.join(
#         "../../tests/regression_tests",
#         BASELINE_FOLDER_NAME_AUGMENTATION,
#         output_file_name,
#     )

#     with open(file_path, "w") as f:
#         json.dump(traces_dict, f)

#     logger.warning("the file has been store in the following location: " + file_path)

# COMMAND ----------


def store_regression_test_case(
    inputs,
    response,
    filename_keys=["source"],
    trace_name="financial_analysis_chain",
):
    """
    Stores the chain output as a JSON file. The JSON file is saved in a predefined directory.

    Args:
        inputs: The input data to be stored.
        response: The output of the chain to be stored.
        trace_name (str): The name of the trace to be used for storing the output. Defaults to "financial_analysis_chain".
        filename_keys (List[str], optional): The list of keys to be used to construct the filename. Defaults to ["source"]
    """

    # this is to make sure that the cache endpoint is used to store the test case
    assert "apim" in os.environ["AZURE_OPENAI_ENDPOINT"]
    assert "responses" in list(response.keys())

    results_dict = {"responses": response["responses"], "inputs": inputs}
    output_file_name = ""
    for key in filename_keys:
        sub_filename = results_dict["inputs"][key].split("/")[-1].replace(".pdf", "")
        if sub_filename:
            if output_file_name:
                output_file_name = output_file_name + "_" + sub_filename
            else:
                output_file_name = sub_filename
    output_file_name += ".json"
    file_path = os.path.join("../tests/regression_tests", trace_name, output_file_name)
    with open(file_path, "w") as f:
        json.dump(results_dict, f)

    logger.warning("the file has been store in the following location: " + file_path)


# COMMAND ----------


def create_session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    unique_part = uuid.uuid4().hex[:8]
    return f"{timestamp}_{unique_part}"
