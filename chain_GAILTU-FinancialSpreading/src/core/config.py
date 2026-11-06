"""
Configration of paths and setup of environment variables for financial spreading project.
Import this to main notebook to setup the openai and storage account.
"""

import os
from databricks.sdk.runtime import dbutils, spark

class Settings:
    # os.environ["AZURE_OPENAI_API_KEY"] = dbutils.secrets.get(
    #     scope="azure-key-vault-scope", key="openai-apim-api-key"
    #     )
    os.environ["AZURE_OPENAI_ENDPOINT"] = "https://msc-apim-gailtu-prd.azure-api.net/openai-api"

    # access to storage account has changed to this method os.environ["STORAGE_ACCOUNT"] = "mscsta{ci_code}{env}".format(ci_code=os.environ["CI_CODE"], env=os.environ["ENVIRONMENT"])
    os.environ["STORAGE_ACCOUNT"] = "mscstagailtuprd03"
    
    os.environ["ENVIRONMENT"] = "prd"

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
    subfolder = 'FinancialSpreading'
    # # List files directly — no mount required
    path = f"abfss://{FOLDER_NAME}@{storage_host}/{subfolder}"
    # dbutils.fs.ls(path)


    # --- Azure OpenAI ---
    openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-5.6-luna"
    azure_openai_api_version: str = "2024-10-21"

    # --- LLM parameters ---
    llm_temperature: float = 0.0
    llm_top_p: float = 1.0
    llm_seed: int = 1234

    # --- Page selection ---
    first_n_pages = 5
    page_score_threshold = 1
    min_pages = 30
    max_selected_pages = 25
    max_adjacent_pages = 5
    refinement_attempts = 0

    # first_n_pages = 75
    # page_score_threshold = 1
    # min_pages = 30
    # max_selected_pages = 10
    # max_adjacent_pages = 2
    # refinement_attempts = 0


    # --- Sharepoint ---
    sharepoint_link = "https://connect2dll.sharepoint.com/:b:/r/sites/Grp-FinancialSpreading/Shared%20Documents/General/5.%20Input%20data"

    paths = [
        {
            'name': 'input_path',
            'type': 'Azure blob storage',
            'reference': '/mnt/projects/FinancialSpreading/InputData',
            'comment': 'Input location for storing annual reports for each country'
        },
        {
            'name': 'output_path',
            'type': 'Azure blob storage',
            # 'reference': '/mnt/projects/FinancialSpreading/OutputData', #Old way of writing
            'reference': f"abfss://{FOLDER_NAME}@{storage_host}/{subfolder}/OutputData",
            'comment': 'Output location for storing annual reports for each country'
        },   
    ]
                                                          
def get_settings() -> Settings:
    return Settings()

