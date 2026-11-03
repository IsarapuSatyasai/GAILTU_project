import os

import mlflow
import pandas as pd
import yaml

# should be relative to the
CONDA_ENV_PATH = "../environment.yml"
SCRIPTS_PATH = "../custom_lcel_components/"
VALIDATION_ARTIFACT_FILE_NAME = "validation.json"
TEST_MODEL_NAME = "TEST_MODEL"
PROMPT_FIELD_NAME = "question"
DEV_ENV_NAME = "prd"
ARTIFACT_NAME = "chain"
AZURE_KEY_VAULT_SCOPE = "azure-key-vault-scope"
AZURE_OPENAI_ACCESS_KEY = "openai-apim-api-key"
AZURE_STORAGE_ACCESS_KEY = "sta-eu-accesskey"


def log_chain(
    lc_chain,
    input_example: dict,
    validation_df: pd.DataFrame = pd.DataFrame(),
    scripts_path: list = [],
    conda_env_path=None,
    signature=None,
):
    if not scripts_path:
        scripts_path = [SCRIPTS_PATH]

    if not conda_env_path:
        conda_env_path = CONDA_ENV_PATH

    if len(validation_df) > 0:
        for key in input_example.keys():
            assert key in list(validation_df.keys())
        assert PROMPT_FIELD_NAME in list(validation_df.keys())

    """Conda environment for the model"""
    with open(conda_env_path) as f:
        conda_env = yaml.load(f, Loader=yaml.FullLoader)

    signature = signature

    """Log the model with a custom functionality for mlflow"""
    with mlflow.start_run():
        logged_model = mlflow.langchain.log_model(
            lc_model=lc_chain,
            name=ARTIFACT_NAME,
            conda_env=conda_env,
            code_paths=scripts_path,
            # input_example=input_example,
            signature=signature,
        )
        if len(validation_df) > 0:
            mlflow.log_dict(
                validation_df.to_dict(orient="records"), VALIDATION_ARTIFACT_FILE_NAME
            )
    return logged_model.model_uri, str(logged_model.registered_model_version)


def get_args(dbutils=None):
    # This is only a formality to be able to pass the tests for logging and loading langchain models, it will be set at deployment time
    if dbutils:
        os.environ["OPENAI_API_KEY"] = dbutils.secrets.get(
            scope=AZURE_KEY_VAULT_SCOPE, key=AZURE_OPENAI_ACCESS_KEY
        )
        os.environ["SA_ACCESSKEY"] = dbutils.secrets.get(
            scope=AZURE_KEY_VAULT_SCOPE, key=AZURE_STORAGE_ACCESS_KEY
        )

    if dbutils:
        model_name = dbutils.widgets.get("model_name")
        environment = dbutils.widgets.get("environment_full_name")

    else:
        model_name = TEST_MODEL_NAME
        environment = DEV_ENV_NAME
    if model_name == TEST_MODEL_NAME:
        """If local execution, get arguments from execution runtime"""
        # parser = argparse.ArgumentParser()
        # parser.add_argument("-oao", "--openai_uri", type=str)
        # args = parser.parse_args()
        # openai_uri = args.openai_uri
        validation_data_path = None
    else:
        """If execution in dbr get arguments from the notebook"""
        # openai_uri = dbutils.widgets.get("openai_uri")
        try:
            validation_data_path = dbutils.widgets.get("validation_data_path")
        except Exception:
            validation_data_path = None
    # return openai_uri, validation_data_path, model_name
    return validation_data_path, model_name, environment
