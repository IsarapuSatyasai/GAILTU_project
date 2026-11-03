"""This module provides functions to interact with Azure Blob Storage for downloading files."""

import logging
import os
from typing import List, Tuple, Union

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)


def _get_blob_names(
    cloud_path: str, blob_service_client: BlobServiceClient
) -> Tuple[List[str], str]:
    """
    Retrieves the names of blobs from a specified cloud path within a storage account.

    This function takes a cloud path and a BlobServiceClient, and retrieves the names of all blobs
    that match the specified path within the storage account. It returns a list of blob names and the container name.

    Args:
        cloud_path (str): The path within the cloud storage to list blobs from.
        blob_service_client (BlobServiceClient): The client to interact with the Azure Blob Storage service.

    Returns:
        Tuple[List[str], str]: A tuple containing a list of blob names and the container name.
    """
    split_path = cloud_path.split("/")
    container_name = split_path.pop(0)
    file_or_folder_path = os.path.join(*split_path)

    # list all blobs
    blobs = blob_service_client.get_container_client(container_name).list_blobs(
        name_starts_with=file_or_folder_path
    )
    return blobs, container_name


def _download_supported_blobs(
    local_dir: str,
    container_name: str,
    blob_names: List[str],
    blob_service_client: BlobServiceClient,
) -> List[str]:
    """
    Downloads supported blobs (.pdf, .doc, .docx) from a specified container in Azure Blob Storage to a local directory.

    This function takes a list of blob names and downloads each blob from the specified container
    in Azure Blob Storage to a local directory. The local file paths of the downloaded blobs are returned.

    Args:
        local_dir (str): The local directory where the blobs will be downloaded.
        container_name (str): The name of the container in Azure Blob Storage.
        blob_names (List[str]): A list of blob names to be downloaded.
        blob_service_client (BlobServiceClient): The client to interact with the Azure Blob Storage service.

    Returns:
        List[str]: A list of local file paths where the blobs have been downloaded.
    """
    supported_extensions = (".pdf", ".doc", ".docx")
    downloaded_file_names = []
    for blob in blob_names:
        if not blob.name.lower().endswith(supported_extensions):
            continue
        blob_client = blob_service_client.get_blob_client(
            container=container_name, blob=blob.name
        )
        local_destination = os.path.join(local_dir, container_name, blob.name)

        _ensure_directories_exist(local_destination)

        with open(local_destination, "wb") as f:
            download_stream = blob_client.download_blob()
            f.write(download_stream.readall())

        downloaded_file_names.append(local_destination)

    return downloaded_file_names


def _ensure_directories_exist(file_path: str):
    """
    Ensures that the directory for a given file path exists.

    This function checks if the directory for the specified file path exists.
    If the directory does not exist, it creates the directory. It logs a warning
    message indicating whether the directory was created or already existed.

    Args:
        file_path (str): The file path for which to ensure the directory exists.
    """
    directory = os.path.dirname(file_path)

    # Check if the directory exists
    if not os.path.exists(directory):
        # Create the directory if it does not exist
        os.makedirs(directory)
        logger.warning(f"created directory: {directory}")
    else:
        logger.warning(f"directory already exists: {directory}")


def _check_valid_input_path(path: str) -> bool:
    """
    Checks if the input path is valid for ingestion.

    This function validates the input path to ensure it meets the required format for ingestion.
    The path must contain at least two levels (e.g., 'container_name/main_folder/...') and end with a '/' if it is a folder.
    If the path is invalid, a warning message is logged.

    Args:
        path (str): The input path to be validated.

    Returns:
        bool: True if the path is valid, False otherwise.
    """
    if len(path.split("/")) <= 2:
        if ".pdf" not in path and path[-1] != "/":
            logger.warning("nothing is ingested: folder path should end with '/'")
        else:
            logger.warning(
                "nothing is ingested: folder path must at least contain two levels like 'container_name/main_folder/..'"
            )
        return False
    return True


def download_files_from_storage_account(
    cloud_path: Union[str, List[str]], tmpdir: str, storage_account: str
) -> List[str]:
    """
    Downloads files from a specified cloud storage account to a local directory.

    This function takes a cloud path (a single file path or a list of file paths),
    a temporary directory, and a storage account name, and downloads the files
    from the specified cloud storage account to the local directory. Folder-like
    paths are not supported and will raise an error.

    Args:
        cloud_path (Union[str, List[str]]): A single file path or a list of file paths within the cloud storage.
        tmpdir (str): The local directory where the files will be downloaded.
        storage_account (str): The name of the storage account.

    Returns:
        List[str]: A list of local file paths where the files have been downloaded.
    """

    def _is_folder_like(path: str) -> bool:
        """
        Treats paths ending with a slash/backslash or without a file extension as folder-like.
        Azure Blob Storage uses virtual directories; this check avoids such inputs.
        """
        if path is None:
            return True
        p = path.strip()
        # If empty or ends with slash/backslash, it's folder-like
        if p == "" or p.endswith("/") or p.endswith("\\"):
            return True
        # If no extension, treat as folder-like
        return os.path.splitext(p)[1] == ""

    # Ensure target directory exists (as stated in docstring)
    os.makedirs(tmpdir, exist_ok=True)

    # Validate cloud_path: must be a single file path (str) or a list of file paths (List[str]).
    # Reject folder-like inputs.
    if isinstance(cloud_path, str):
        if _is_folder_like(cloud_path):
            raise ValueError(
                "cloud_path must be a file path or a list of file paths; folder paths are not supported."
            )
        paths_to_fetch: List[str] = [cloud_path]
    elif isinstance(cloud_path, list):
        if not cloud_path:
            raise ValueError("cloud_path list must not be empty.")
        if not all(isinstance(p, str) for p in cloud_path):
            raise ValueError("cloud_path list must contain only strings.")
        folder_like = [p for p in cloud_path if _is_folder_like(p)]
        if folder_like:
            raise ValueError(
                "cloud_path must contain only file paths; folder paths are not supported. "
                f"Invalid entries: {folder_like}"
            )
        paths_to_fetch = cloud_path
    else:
        raise ValueError(
            "cloud_path must be a string (file path) or a list of strings (file paths)."
        )

    logger.warning("Using the following storage account: " + storage_account)

    # set blobservice client
    if "SA_ACCESSKEY" in os.environ:
        logger.warning("Using SA_ACCESSKEY from environment variables.")
        credential = os.environ["SA_ACCESSKEY"]
    else:
        logger.warning(
            "Using DefaultAzureCredential for authentication. Ensure your environment is configured correctly."
        )
        credential = DefaultAzureCredential()
    try:
        blob_service_client = BlobServiceClient(
            account_url="https://" + storage_account + ".blob.core.windows.net/",
            credential=credential,
        )
    except Exception as e:
        raise ValueError("Failed to create blob service client: " + str(e))

    # Resolve blob names and container(s) for each provided file path using the existing helper.
    all_blob_names: List[str] = []
    container_name_for_first: str = ""
    try:
        for idx, single_path in enumerate(paths_to_fetch):
            blob_names, container_name = _get_blob_names(
                single_path, blob_service_client
            )
            # Keep track of container name from the first call; subsequent calls should match
            if idx == 0:
                container_name_for_first = container_name
            elif container_name != container_name_for_first:
                # If needed, you can relax this constraint and perform multiple downloads across containers.
                # Keeping strict to minimize changes and maintain predictable behavior.
                raise ValueError(
                    "All file paths must belong to the same container. "
                    f"Found '{container_name_for_first}' and '{container_name}'."
                )
            all_blob_names.extend(blob_names)
    except Exception as e:
        raise ValueError("Failed to get blob names: " + str(e))

    # Download using the existing helper
    try:
        downloaded_file_names = _download_supported_blobs(
            tmpdir, container_name_for_first, all_blob_names, blob_service_client
        )
    except Exception as e:
        # Keep message same as your original code
        raise ValueError("Failed to get blob names: " + str(e))

    if len(downloaded_file_names) == 0:
        raise ValueError("No files found at the given path")

    return downloaded_file_names
