# Databricks notebook source
# MAGIC %md
# MAGIC # 1. Install libraries

# COMMAND ----------

import os
import sys
import inspect

# COMMAND ----------

print('Current working directory:', os.getcwd())

# COMMAND ----------

print('Current working directory:', os.getcwd())

# COMMAND ----------

shared_functions_path = "../utils"

if shared_functions_path not in sys.path:
    sys.path.insert(0, shared_functions_path)
    sys.path.insert(0, "../chain_GAILTU-FinancialSpreading/src/core")

# COMMAND ----------

# DBTITLE 1,Install requirements
# MAGIC %pip install -r ../utils/requirements.txt

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. import functions

# COMMAND ----------

from custom_lcel_components.ingest import ingest_documents

# COMMAND ----------

from custom_lcel_components.llm import calculate_cost_llm

# COMMAND ----------

from custom_lcel_components.ingest import _get_pdf_loader

# COMMAND ----------

print(inspect.getsource(custom_lcel_components.ingest))

# COMMAND ----------

print(inspect.getsource(calculate_cost_llm))

# COMMAND ----------

from spreading_utils.config import *

# COMMAND ----------

"/dbfs/mnt/projects/FinancialSpreading/InputData/NL/Adyen/Adyen-report.pdf"

for item in paths:
    globals()[item['name']] = item['reference']
    print(item['name']," = ", item['reference'])

# COMMAND ----------

print(inspect.getsource(ingest_documents))

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. load pdf 

# COMMAND ----------

pdf_file = "/dbfs"+input_path+"/NL/Adyen/Adyen-report.pdf"

# COMMAND ----------

# MAGIC %md
# MAGIC ## a.pyPDFLoader

# COMMAND ----------

from langchain_community.document_loaders import PyPDFLoader

# COMMAND ----------

loader = PyPDFLoader(pdf_file)
documents = loader.load()

# COMMAND ----------

print("Number of pages loaded:", len(documents))
print("Metadata on first page:", documents[0].metadata)
print("Page 1 text snippet:\n", documents[0].page_content[:500])

# COMMAND ----------

print("Metadata on balance sheet:", documents[193].metadata)
print("Page 194 text snippet:\n", documents[193].page_content[:])

# COMMAND ----------

# MAGIC %md
# MAGIC ## b. pyMuPDFLoader

# COMMAND ----------

from langchain_community.document_loaders import PyMuPDFLoader

# COMMAND ----------

loader = PyMuPDFLoader(pdf_file, mode="page")
documents = loader.load()

# COMMAND ----------

print("Number of pages loaded:", len(documents))
print("Metadata on first page:", documents[0].metadata)
print("Page 1 text snippet:\n", documents[0].page_content[:500])

# COMMAND ----------

print("Metadata on balance sheet:", documents[193].metadata)
print("Page 194 text snippet:\n", documents[193].page_content[:])

# COMMAND ----------

documents[193].page_content[:]

# COMMAND ----------

loader = PyMuPDFLoader(pdf_file, mode="page")
documents = loader.load()

# COMMAND ----------

# MAGIC %md
# MAGIC ## c. PDFPlumberLoader

# COMMAND ----------

from langchain_community.document_loaders import PDFPlumberLoader

# COMMAND ----------

pip install pdfplumber

# COMMAND ----------

loader = PDFPlumberLoader(pdf_file)
docs = loader.load()

# COMMAND ----------

print("Number of pages loaded:", len(docs))
print("Metadata on first page:", docs[0].metadata)
print("Page 1 text snippet:\n", docs[0].page_content[:500])

# COMMAND ----------

print("Metadata on balance sheet:", docs[193].metadata)
print("Page 194 text snippet:\n", docs[193].page_content[:])

# COMMAND ----------

# MAGIC %md
# MAGIC ## d. UnstructuredPDFLoader

# COMMAND ----------

from langchain_community.document_loaders import UnstructuredPDFLoader

# COMMAND ----------

pip install unstructured pi_heif unstructured_inference pdf2image ml_dtypes

# COMMAND ----------

pip install onnx==1.18

# COMMAND ----------

loader = UnstructuredPDFLoader(pdf_file, strategy="fast", mode="single")
docs = loader.load()

# COMMAND ----------

print("Number of pages loaded:", len(docs))
print("Metadata on first page:", docs[0].metadata)
print("Page 1 text snippet:\n", docs[0].page_content[:500])

# COMMAND ----------

print("Metadata on balance sheet:", docs[193].metadata)
print("Page 194 text snippet:\n", docs[193].page_content[:])

# COMMAND ----------

# MAGIC %md
# MAGIC ## e. Docling

# COMMAND ----------

pip install langchain-docling

# COMMAND ----------

from langchain_docling.loader import DoclingLoader

# COMMAND ----------

loader = DoclingLoader(pdf_file)
docs = loader.load()

# COMMAND ----------

print("Number of pages loaded:", len(docs))
print("Metadata on first page:", docs[0].metadata)
print("Page 1 text snippet:\n", docs[0].page_content[:500])

# COMMAND ----------

docs[1810].metadata['dl_meta']['doc_items'][0]['prov'][0]['page_no']

# COMMAND ----------

print("Metadata on balance sheet:", docs[1804].metadata)
print("Page 194 text snippet:\n", docs[1804].page_content[:])

# COMMAND ----------

print("Metadata on balance sheet:", docs[1805].metadata)
print("Page 194 text snippet:\n", docs[1805].page_content[:])

# COMMAND ----------

print("Metadata on balance sheet:", docs[1806].metadata)
print("Page 194 text snippet:\n", docs[1806].page_content[:])

# COMMAND ----------

print("Metadata on balance sheet:", docs[1807].metadata)
print("Page 194 text snippet:\n", docs[1807].page_content[:])

# COMMAND ----------

print("Metadata on balance sheet:", docs[1808].metadata)
print("Page 194 text snippet:\n", docs[1808].page_content[:])

# COMMAND ----------

print("Metadata on balance sheet:", docs[1809].metadata)
print("Page 194 text snippet:\n", docs[1809].page_content[:])

# COMMAND ----------

print("Metadata on balance sheet:", docs[1810].metadata)
print("Page 194 text snippet:\n", docs[1810].page_content[:])
