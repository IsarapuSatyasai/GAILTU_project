# Databricks notebook source
# MAGIC %md # LTU - Update Financial Product Catalogue
# MAGIC ##Purpose of the Notebook
# MAGIC This notebook is used to update the Financial Product Catalogue, including commercial financial information. The source data is provided by Beelaard, P (Peter) and can be accessed via the following SharePoint link: https://connect2dll.sharepoint.com/sites/Grp-ProductManagement/Shared%20Documents/Forms/AllItems.aspx?FolderCTID=0x012000E379EF16036EBC42AA3B448487D7ACE1&id=%2Fsites%2FGrp%2DProductManagement%2FShared%20Documents%2FGeneral%2FProduct%20Analysis%2FReconciliation%20Matrix&ovuser=07751f8b%2D9617%2D49d5%2D9024%2D85f034f400ec%2CWuQ%40delagelanden%2Ecom&OR=Teams%2DHL&CT=1750930992389&clickparams=eyJBcHBOYW1lIjoiVGVhbXMtRGVza3RvcCIsIkFwcFZlcnNpb24iOiI0OS8yNTA2MDIwNjYxNiIsIkhhc0ZlZGVyYXRlZFVzZXIiOmZhbHNlfQ%3D%3D
# MAGIC
# MAGIC Once the source file is updated, it must be manually downloaded and uploaded to the designated storage account at the specified path. 
# MAGIC - Financial Product Catalogue: projects/LTU/Financial Product Catalogue/Matrix.xlsx
# MAGIC - Financial Product Catalogue (CF): projects/LTU/Financial Product Catalogue/CF Matrix.xlsx
# MAGIC
# MAGIC After this step, the notebook should be executed to refresh the Financial Product Catalogue with the latest information.

# COMMAND ----------

# MAGIC %run ../utils/databricks_scripts/storage_operations

# COMMAND ----------

import os 
import unicodedata
from typing import Any, Union, Mapping, Sequence

# COMMAND ----------


def create_financial_product_dict(country: str, financial_product_catalogue: dict) -> dict:
    """
    Constructs a nested dictionary of financial products for a given country, 
    using a provided financial product catalogue.

    For each row in the country's DataFrame:
    - If the 'PARC Product' contains 'Servitization Bucket' and the classification is 
      'Financial Lease', appends ' (FL)' to the 'Local Product' value.
    - If the classification is 'Operating Lease', appends ' (OL)' to the 'Local Product' value.
    - Builds a nested dictionary where each 'PARC Product' maps to a dictionary of 
      'Local Product' keys and their corresponding customer-facing descriptions.

    Args:
        country (str): The country key to extract the relevant DataFrame from the catalogue.
        financial_product_catalogue (dict): A dictionary where each key is a country and 
            each value is a pandas DataFrame containing financial product data.

    Returns:
        dict: A nested dictionary structured as {PARC Product: {Local Product: Description}}.
    """
    financial_product_catalogue_df = financial_product_catalogue[country]
    nested_dict = {} 
    
    # Identify rows where 'PARC Product' contains 'Servitization Bucket'
    bucket_mask = financial_product_catalogue_df["PARC Product"].str.contains("Servitization Bucket", na=False)

    # Condition for Financial Lease
    fl_mask = financial_product_catalogue_df["Classification for DLL \n(IFRS/US GAAP Accounting)"] == "Financial Lease"

    # Condition for Operating Lease
    ol_mask = financial_product_catalogue_df["Classification for DLL \n(IFRS/US GAAP Accounting)"] == "Operating Lease"

    # Apply both conditions within the Servitization Bucket rows
    financial_product_catalogue_df.loc[bucket_mask & fl_mask, "Local Product"] += " (FL)"
    financial_product_catalogue_df.loc[bucket_mask & ol_mask, "Local Product"] += " (OL)"

    for _, row in financial_product_catalogue_df.iterrows():
        parc = row["PARC Product"]
        local = row["Local Product"]
        desc = row["Short description of the Product\n(Customer view)"]
        
        if parc not in nested_dict:
            nested_dict[parc] = {}
        nested_dict[parc][local] = desc
    
    return nested_dict

def create_cf_financial_product_dict(country: str, cf_financial_product_catalogue: dict) -> dict:
    """
    Creates a nested dictionary of CF financial products for a given country from a raw product catalogue.

    Parameters:
    country (str): The country for which the financial product dictionary is to be created.
    cf_financial_product_catalogue (dict): A dictionary where keys are country names and values are
                                           DataFrames containing CF financial product catalogue data.

    Returns:
    dict: A nested dictionary mapping PARC Product Groups to Local Products and their descriptions.
    """
    # Extract the DataFrame for the specified country
    cf_financial_product_catalogue_df = cf_financial_product_catalogue[country]

    # Clean the DataFrame using the predefined cleaning function
    cf_financial_product_catalogue_df_cleaned = clean_cf_financial_product_catalogue(cf_financial_product_catalogue_df)

    # Initialize an empty dictionary to hold the nested structure
    nested_dict = {}

    # Iterate over each row in the cleaned DataFrame
    for _, row in cf_financial_product_catalogue_df_cleaned.iterrows():
        parc = row["PARC Product Group"]  # Top-level category
        local = row["Local Product"]      # Sub-category or specific product
        desc = row["Short description of the Product\n(Customer view)"]  # Product description

        # Create a new sub-dictionary if the PARC group is not yet in the nested dictionary
        if parc not in nested_dict:
            nested_dict[parc] = {}

        # Map the local product to its description under the corresponding PARC group
        nested_dict[parc][local] = desc

    return nested_dict

# COMMAND ----------

def clean_dict(data):
    """
    Recursively removes non-breaking space characters (`\xa0`) from both keys and values
    in a dictionary. Also handles nested dictionaries and lists.

    Parameters:
        data (dict | list | str | any): The input data structure to clean. Can be a dictionary,
        list, string, or any other type.

    Returns:
        The cleaned version of the input with all `\xa0` characters replaced by regular spaces
        in dictionary keys and string values. Non-string values are returned unchanged.
    """
    if isinstance(data, dict):
        return {
            str(k).replace("\xa0", " ").strip(): clean_dict(v)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [clean_dict(item) for item in data]
    elif isinstance(data, str):
        return data.replace("\xa0", " ").strip()
    else:
        return data
    
def clean_cf_financial_product_catalogue(df):
    """
    Cleans the CF Financial Product Catalogue DataFrame by:
    1. Setting the first row as column headers.
    2. Removing the first two rows which contain metadata or explanatory text.
    3. Dropping rows where 'Local Product' or 'PARC Product Group' are missing.

    Parameters:
    df (pd.DataFrame): Raw DataFrame containing the financial product catalogue.

    Returns:
    pd.DataFrame: Cleaned DataFrame with valid product entries.
    """
    # Set the first row as the column headers
    df.columns = df.iloc[0]

    # Drop the first row (now redundant) and reset the index
    df_cleaned = df[1:].reset_index(drop=True)

    # Drop the second row, which contains explanatory text rather than actual data
    df_cleaned = df_cleaned.iloc[1:].reset_index(drop=True)

    # Create a mask to identify rows where either 'Local Product' or 'PARC Product Group' is missing
    mask = df_cleaned["Local Product"].isna() | df_cleaned["PARC Product Group"].isna()

    # Remove rows with missing critical product information
    df_cleaned = df_cleaned[~mask]

    # remove unexpected \n
    df_cleaned['Local Product'] = df_cleaned['Local Product'].str.replace('\n', '', regex=False)

    return df_cleaned

# COMMAND ----------

def _strip_str(s: str) -> str:
    """Remove diacritics from a single string and return ASCII-safe text."""
    if s is None:
        return s
    normalized = unicodedata.normalize('NFKD', s)
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch)) \
             .encode('ascii', 'ignore').decode('ascii')

def strip_diacritics_to_ascii(
    obj: Any,
    *,
    normalize_keys: bool = False
) -> Any:
    """
    Convert text to an ASCII-safe form by removing diacritics.
    Works for strings and recursively for nested containers (dict, list, tuple, set).

    Examples:
        strip_diacritics_to_ascii("Umowa pożyczki")
        -> "Umowa pozyczki"

        strip_diacritics_to_ascii({"title": "Zażółć gęślą jaźń"})
        -> {"title": "Zazolc gesla jazn"}

        strip_diacritics_to_ascii(
            {"kółko": ["café", {"naïve": "résumé"}]},
            normalize_keys=True
        )
        -> {"kolko": ["cafe", {"naive": "resume"}]}

    Parameters
    ----------
    obj : Any
        Input object: str, dict, list, tuple, set, or nested combinations.
    normalize_keys : bool, default False
        If True, also strip diacritics from dict keys that are strings.

    Returns
    -------
    Any
        Structure-preserving object with all strings converted to ASCII-safe text.
    """
    # Handle strings directly
    if isinstance(obj, str):
        return _strip_str(obj)

    # Preserve None
    if obj is None:
        return None

    # Dict: process keys (optional) and values recursively
    if isinstance(obj, Mapping):
        if normalize_keys:
            return {
                (_strip_str(k) if isinstance(k, str) else k): strip_diacritics_to_ascii(v, normalize_keys=normalize_keys)
                for k, v in obj.items()
            }
        else:
            return {
                k: strip_diacritics_to_ascii(v, normalize_keys=normalize_keys)
                for k, v in obj.items()
            }

    # List / Tuple / Set: process each element, preserve type
    if isinstance(obj, (list, tuple, set)):
        converted = [strip_diacritics_to_ascii(x, normalize_keys=normalize_keys) for x in obj]
        if isinstance(obj, list):
            return converted
        if isinstance(obj, tuple):
            return tuple(converted)
        return set(converted)

    # Other types: return unchanged


# COMMAND ----------

financial_product_catalogue = read_excel("projects/LTU/Financial Product Catalogue/Matrix 21042026.xlsx", sheet_name=None)
cf_financial_product_catalogue = read_excel("projects/LTU/Financial Product Catalogue/CF Matrix 23012026.xlsx", sheet_name=None)

# COMMAND ----------

for sheet_name, df in financial_product_catalogue.items():
    print(f"Sheet name: {sheet_name}")

# COMMAND ----------

for sheet_name, df in cf_financial_product_catalogue.items():
    print(f"Sheet name: {sheet_name}")

# COMMAND ----------

selected_countries_names = ["3_BELGIUM", "2_NETHERLANDS", "2_FRANCE", "1_GERMANY", "2_ITALY", "1_UK", "3_IRELAND", "3_DENMARK", "3_FINLAND", "3_NORWAY", "3_POLAND", "3_SWEDEN", "2_SPAIN", "2_PORTUGAL", "1_Australia", "3_SWITZERLAND"]
cf_selected_countries_names = ["Belgium", "Netherlands", "France", "Germany", "Italy", "UK", "Ireland", "Denmark", "Finland", "Norway", "Poland", "Sweden", "Spain", "Portugal", "Australia", "Switzerland"]
selected_countries_names_fpd_dict = ["be_fpc_dict", "nl_fpc_dict", "fr_fpc_dict", "de_fpc_dict", "it_fpc_dict", "uk_fpc_dict", "ie_fpc_dict", "dk_fpc_dict", "fi_fpc_dict", "no_fpc_dict", "pl_fpc_dict", "se_fpc_dict", "es_fpc_dict", "pt_fpc_dict", "au_fpc_dict", "ch_fpc_dict"]

# # Define the output file path
output_file_path = f"../chain_GAILTU/src/core/financial_product_catalogue_dec.py"

# Ensure the directory exists
os.makedirs(os.path.dirname(output_file_path), exist_ok=True) if os.path.dirname(output_file_path) else None

# Initialize a dictionary to hold reformatted country names and variable names
fpc_local_product_dec_entries = {}

# Open the output file for writing all dictionaries
with open(output_file_path, "w") as f:
    fpc_product_dec_dict = dict(zip(financial_product_catalogue["Product Descriptions"]["Product Name"], financial_product_catalogue["Product Descriptions"]["Product Description"]))
    fpc_product_dec_dict_cleaned = clean_dict(fpc_product_dec_dict)
    fpc_product_dec_dict_cleaned = strip_diacritics_to_ascii(fpc_product_dec_dict_cleaned, normalize_keys=True)

    # Check and expand the combined key, Servitization Bucket 2 - 4 share the same descriptions
    if "Servitization Bucket 2 - 4" in fpc_product_dec_dict_cleaned:
        value = fpc_product_dec_dict_cleaned["Servitization Bucket 2 - 4"]
        for i in range(2, 5):
            fpc_product_dec_dict_cleaned[f"Servitization Bucket {i}"] = value
        del fpc_product_dec_dict_cleaned["Servitization Bucket 2 - 4"]
    
    # Find the index of the row where 'PARC Product Group' is 'CF Product Variations', since the information above 'CF Product Variations' is identical to that in Matrix.xlsx, it is not necessary to use it for updating the product description.
    cf_financial_product_catalogue_glossary = cf_financial_product_catalogue["Glossary"]
    start_index = cf_financial_product_catalogue_glossary[cf_financial_product_catalogue_glossary["PARC Product Group"] == "CF Product Variations"].index

    # If such a row exists, select all rows after it
    if not start_index.empty:
        cf_financial_product_catalogue_dec = cf_financial_product_catalogue_glossary.iloc[start_index[0] + 1:]
    else:
        cf_financial_product_catalogue_dec = pd.DataFrame()  # or handle the case where the value is not found

    if not cf_financial_product_catalogue_dec.empty:
        cf_fpc_product_dec_dict = dict(zip(cf_financial_product_catalogue_dec["PARC Product Group"], cf_financial_product_catalogue_dec["Definition"]))
        cf_fpc_product_dec_dict_cleaned = strip_diacritics_to_ascii(cf_fpc_product_dec_dict, normalize_keys=True)
        fpc_product_dec_dict_cleaned.update(cf_fpc_product_dec_dict_cleaned)

    f.write(f"fpc_product_dec_dict = {json.dumps(fpc_product_dec_dict_cleaned, indent=4)}\n\n")

    for i in range(len(selected_countries_names)):
        country_name = selected_countries_names[i]
        dict_var_name = selected_countries_names_fpd_dict[i]
        fpc_dict = create_financial_product_dict(country_name, financial_product_catalogue)
        fpc_dict_cleaned = clean_dict(fpc_dict)
        fpc_dict_cleaned = strip_diacritics_to_ascii(fpc_dict_cleaned, normalize_keys=True)

        # Add CF fpc_dict to fpc_dict_cleaned
        cf_country_name = cf_selected_countries_names[i]
        cf_fpc_product_dec_dict = create_cf_financial_product_dict(cf_country_name, cf_financial_product_catalogue)
        cf_fpc_product_dec_dict_cleaned = strip_diacritics_to_ascii(cf_fpc_product_dec_dict, normalize_keys=True)
        fpc_dict_cleaned.update(cf_fpc_product_dec_dict_cleaned)

        # Write each dictionary to the file as a variable
        f.write(f"{dict_var_name} = {json.dumps(fpc_dict_cleaned, indent=4)}\n\n")

        # Reformat country name (e.g., '3_BELGIUM' -> 'Belgium')
        # Keep UK as 'UK', others capitalize normally
        reformatted_name = cf_country_name if cf_country_name == "UK" else cf_country_name.capitalize()

        print(reformatted_name)

        # Update the master dictionary
        fpc_local_product_dec_entries[reformatted_name] = dict_var_name

        if not set(fpc_dict_cleaned.keys()).issubset(fpc_product_dec_dict_cleaned.keys()):
            print(f"The set includes all of {country_name}'s product descriptions.")
        else: 
            missing_keys = set(fpc_dict_cleaned.keys()) - set(fpc_product_dec_dict_cleaned.keys())
            print(f"The following product descriptions are missing from the {country_name} set. \n {missing_keys}" )

    # Write the master dictionary to the file
    f.write("fpc_local_product_dec_dicts = {\n")
   
    for country, var_name in fpc_local_product_dec_entries.items():
        if country == "UK":
            f.write(f'    "{country}": {var_name},\n')
            f.write(f'    "AGCO Finance UK": {var_name},\n')
        elif country == "France":
            f.write(f'    "{country}": {var_name},\n')
            f.write(f'    "AGCO Finance France": {var_name},\n')
        else:
            f.write(f'    "{country}": {var_name},\n')
    f.write("}\n")


print(f"All individual dictionaries and the master dictionary have been saved to {output_file_path}")


# COMMAND ----------

import sys
sys.path.insert(0, "../chain_GAILTU/src/core")

# COMMAND ----------

from financial_product_catalogue_dec import be_fpc_dict, nl_fpc_dict, fr_fpc_dict, de_fpc_dict, it_fpc_dict, uk_fpc_dict, ie_fpc_dict, dk_fpc_dict, fi_fpc_dict, no_fpc_dict, pl_fpc_dict, se_fpc_dict, es_fpc_dict, pt_fpc_dict, au_fpc_dict, ch_fpc_dict

# COMMAND ----------

# check Product name and Local Product name
selected_countries_names_fpd_dicts = {
    "be_fpc_dict": be_fpc_dict,
    "nl_fpc_dict": nl_fpc_dict,
    "fr_fpc_dict": fr_fpc_dict,
    "de_fpc_dict": de_fpc_dict,
    "it_fpc_dict": it_fpc_dict,
    "uk_fpc_dict": uk_fpc_dict,
    "ie_fpc_dict": ie_fpc_dict,
    "dk_fpc_dict": dk_fpc_dict,
    "fi_fpc_dict": fi_fpc_dict,
    "no_fpc_dict": no_fpc_dict,
    "pl_fpc_dict": pl_fpc_dict,
    "se_fpc_dict": se_fpc_dict,
    "es_fpc_dict": es_fpc_dict,
    "pt_fpc_dict": pt_fpc_dict,
    "au_fpc_dict": au_fpc_dict, 
    "ch_fpc_dict": ch_fpc_dict,
}

for i in range(len(selected_countries_names)):
    country_names = selected_countries_names_fpd_dict[i]
    country_dict = selected_countries_names_fpd_dicts[country_names]

    sorted_keys = sorted(country_dict.keys())

    # Get all nested keys
    nested_keys = set()
    for value in country_dict.values():
        nested_keys.update(value.keys())

    # Sort the nested keys
    sorted_nested_keys = sorted(nested_keys)

    print(country_names)
    print(f"Product name: \n{sorted_keys}")
    print(f"Local Product name: \n{sorted_nested_keys}")

# COMMAND ----------

def get_nested_keys(d):
    """
    Extracts nested keys from a two-level dictionary and returns them sorted
    by top-level key and nested key in the format 'top_key - nested_key'.

    Parameters:
    d (dict): A dictionary where each value is either another dictionary or a non-dict value.

    Returns:
    list: A sorted list of strings representing the nested keys in 'top_key - nested_key' format.
    """
    result = []
    for key, value in d.items():
        if isinstance(value, dict):
            for nested_key in value:
                result.append((key, nested_key))
    return [f"{k} - {nk}" for k, nk in sorted(result)]

# COMMAND ----------

current_fpc = {}
current_fpc["fpc_product_dec_dict"] = fpc_product_dec_dict

# The following code is used to generate input data for setting up a Microsoft Form.
for i in range(len(selected_countries_names)):
    country_names = selected_countries_names_fpd_dict[i]
    country_dict = selected_countries_names_fpd_dicts[country_names]
    print(f"{country_names} (Product Name - Local Product Name)")
    print(get_nested_keys(country_dict))
    print("\n")
    current_fpc[f"{country_names}"] = country_dict

# COMMAND ----------

write_pickle(current_fpc, "projects/LTU/Financial Product Catalogue/fpc_ref_21042026.xlsx")

# COMMAND ----------

pervious_fpc_ref = read_pickle("projects/LTU/Financial Product Catalogue/fpc_ref_23032026.xlsx")

# COMMAND ----------

def dict_diff(d1, d2, path=""):
    """
    Recursively compares two dictionaries and returns a dictionary of differences.

    Each key in the returned dictionary represents a path to a differing value in the input dictionaries.
    The value is a dictionary indicating the type of change:
        - "added": key exists in d2 but not in d1
        - "removed": key exists in d1 but not in d2
        - "changed": key exists in both but values differ
        - Nested dictionaries are compared recursively
    Args:
        d1 (dict): The first dictionary to compare.
        d2 (dict): The second dictionary to compare.
        path (str): Internal parameter used to track the nested key path (default is "").

    Returns:
        dict: A dictionary describing the differences between d1 and d2.
    """
    diffs = {}
    for key in d1.keys() | d2.keys():
        new_path = f"{path}.{key}" if path else key
        val1 = d1.get(key, "<missing>")
        val2 = d2.get(key, "<missing>")

        if key not in d2:
            diffs[new_path] = {
                "status": "removed",
                "d1": val1,
                "d2": "<missing>"
            }
        elif key not in d1:
            diffs[new_path] = {
                "status": "added",
                "d1": "<missing>",
                "d2": val2
            }
        elif isinstance(val1, dict) and isinstance(val2, dict):
            nested_diff = dict_diff(val1, val2, new_path)
            diffs.update(nested_diff)
        elif val1 != val2:
            diffs[new_path] = {
                "status": "changed",
                "d1": val1,
                "d2": val2
            }
    return diffs


# COMMAND ----------

if current_fpc == pervious_fpc_ref:
    print("The current fpc is the same as the pervious fpc.")
else:
    print("The current fpc is different from the pervious fpc.")
    diffs = dict_diff(current_fpc, pervious_fpc_ref)
    for k, v in diffs.items():
        print(f"{k}: {v}")
