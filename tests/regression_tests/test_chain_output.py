import json
import logging
import os
import sys
import warnings
from typing import List

import mlflow

logger = logging.getLogger(__name__)

# Quiet MLflow's own loggers; child loggers (mlflow.*) inherit this level.
logging.getLogger("mlflow").setLevel(logging.ERROR)

sys.path.insert(0, "../../../utils/")


# BASELINE_FOLDER_NAME = "baseline_response"
INPUT_EXAMPLE_FILE_NAME = "input_example.json"
# note that the RAG test checks whether the augmented prompts are consistent. The name of the augmentation step (NAME_OF_AUGMENTATION_STEP) in the chain is used to retrieve corresponding traces.


def load_json_files_from_folder(folder_name: str) -> List[dict]:
    """
    Load all JSON files from a specified folder.

    Args:
        folder_name (str): The name of the folder containing JSON files.

    Returns:
        List[dict]: A list of dictionaries containing the JSON data.
    """
    json_data_list = []

    if not os.path.isdir(folder_name):
        return json_data_list

    # Iterate over all files in the current folder
    for file_name in os.listdir(folder_name):
        warnings.warn("filename: " + file_name)
        # Check if the file is a JSON file
        if file_name.endswith(".json"):
            file_path = os.path.join(folder_name, file_name)
            # Open and load the JSON file
            with open(file_path, "r") as json_file:
                json_data = json.load(json_file)
                json_data_list.append(json_data)
        warnings.warn(
            RuntimeWarning(str(len(json_data_list)) + " files have been ingested...")
        )

    return json_data_list


def test_against_baseline(model_uri: str, chain_name: str):
    """
    Test the model's output against a baseline.

    Args:
        model_uri (str): The URI of the model to be tested.
        chain_name: the folder path where the test cases can be found

    Raises:
        AssertionError: If the model's output does not match the baseline response.
    """
    # Remove mlflow-skinny 3.15 instrumentation BEFORE load_model so no tracer/callback
    # is baked into the loaded chain (that patch deadlocks the sync invoke on CI).
    mlflow.langchain.autolog(disable=True)
    mlflow.llama_index.autolog(disable=True)
    mlflow.tracing.disable()

    logger.warning("loading the model..")
    model_chain = mlflow.langchain.load_model(model_uri)
    model_chain.name = chain_name

    # Load all JSON files from the current folder
    json_files_data = load_json_files_from_folder(chain_name)
    for baseline_dict in json_files_data:
        inputs = baseline_dict["inputs"]
        """Generate responses from the target model"""
        logger.warning("generating the response..")

        generated_response = model_chain.invoke(inputs)

        logger.warning(
            "this is the response: " + json.dumps(generated_response["responses"])
        )
        assert generated_response["responses"] == baseline_dict["responses"]
    warnings.warn(
        str(len(json_files_data)) + " number of responses have been tested..."
    )
