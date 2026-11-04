# Databricks notebook source
# Databricks notebook source
# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# dependencies = [
#   "-r ../utils/requirements.txt",
#   "openpyxl",
# ]
# ///
%pip install -r ../utils/requirements.txt


# COMMAND ----------


# MAGIC %run ../utils/databricks_scripts/storage_operations


# COMMAND ----------

# MAGIC %pip install openpyxl==3.1.3

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

# MAGIC %load_ext autoreload
# MAGIC %autoreload 2


# COMMAND ----------

STORAGE_ACCOUNT_NAME = "mscstagailtuprd03"
FOLDER_NAME = "projects"
TENANT_ID = "07751f8b-9617-49d5-9024-85f034f400ec"
DBR_MI = "fa515616-7575-408d-8196-320484b017c7"

storage_host = f"{STORAGE_ACCOUNT_NAME}.dfs.core.windows.net"

spark.conf.set(f"fs.azure.account.auth.type.{storage_host}", "OAuth")
spark.conf.set(f"fs.azure.account.oauth.provider.type.{storage_host}", "org.apache.hadoop.fs.azurebfs.oauth2.MsiTokenProvider")
spark.conf.set(f"fs.azure.account.oauth2.msi.tenant.{storage_host}", TENANT_ID)
spark.conf.set(f"fs.azure.account.oauth2.client.id.{storage_host}", DBR_MI)

folder = 'FinancialSpreading'
path = f"abfss://{FOLDER_NAME}@{storage_host}/{folder}"
dbutils.fs.ls(path)

# COMMAND ----------

import sys
import os
from datetime import datetime
import logging
import pandas as pd

sys.path.insert(0, "../utils")
sys.path.insert(0, "../chain_GAILTU-FinancialSpreading/src/core")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)

# COMMAND ----------

from config import get_settings

# COMMAND ----------

for item in get_settings().paths:
    globals()[item['name']] = item['reference']
    print(item['name']," = ", item['reference'])

# COMMAND ----------

dbutils.widgets.text("mnt", "/mnt/projects/FinancialSpreading/", "Mount path")
dbutils.widgets.text("template_path", "Test/creditlens_template_for_ai_model.xlsx", "Excel template file path")
dbutils.widgets.text("pdf_file_name", "/NL/Adyen/Adyenreport.pdf", "PDF file name")


# COMMAND ----------

mnt = dbutils.widgets.get("mnt")
template_path = dbutils.widgets.get("template_path")
pdf_file_name = dbutils.widgets.get("pdf_file_name")

file_path = f"abfss://{FOLDER_NAME}@{storage_host}/{folder}/{template_path}"
pdf_source = input_path.removeprefix("/mnt/")+ pdf_file_name

print("PDF source:", pdf_source)
print("Template:", file_path)


# COMMAND ----------

os.environ["AZURE_OPENAI_API_KEY"] = dbutils.secrets.get(scope="azure-key-vault-scope", key="openai-apim-api-key")

# COMMAND ----------

import importlib
import prompts.system_prompt, rag_poc.retrieve, rag_poc.extract
importlib.reload(prompts.system_prompt)  # pick up prompt edits
importlib.reload(rag_poc.retrieve)  # pick up edits to retrieve.py / extract.py without restarting Python
importlib.reload(rag_poc.extract)   # (retrieve first: extract imports retrieve_context from it)

from template.excel_reader import read_xlsx
from rag_poc.ingest import build_index
from rag_poc.extract import extract_all
from rag_poc.retrieve import load_page_texts
import pandas as pd

# Build excel_data the same way read_creditlens_template does
creditlens_dfs = read_xlsx(file_path)
excel_data = []
for worksheet_name, pd_df in creditlens_dfs.items():
    for _, row in pd_df.iterrows():
        variable = row.get("Variable")
        if variable and variable not in ["table_name", "table_description"]:
            excel_data.append({
                "worksheet": worksheet_name,
                "variable": variable,
                "description": row.get("Description") if pd.notna(row.get("Description")) else None,
                "formula": row.get("Formula") if pd.notna(row.get("Formula")) else None,
                "remarks": row.get("Remarks") if pd.notna(row.get("Remarks")) else None,
            })

print("Template metrics:", len(excel_data))

print("Indexing PDF...")
collection_name, config = build_index(pdf_source)
print("Collection:", collection_name)

# Local copy of the PDF so every retrieved passage can be labelled with the page it actually appears on
pdf_abfss = f"abfss://{FOLDER_NAME}@{storage_host}/" + pdf_source.removeprefix(f"{FOLDER_NAME}/")
local_pdf = "/tmp/" + pdf_source.split("/")[-1]
dbutils.fs.cp(pdf_abfss, f"file:{local_pdf}")
page_texts = load_page_texts(local_pdf)
print("PDF pages:", len(page_texts))

years = [2024, 2023]
rag_result = extract_all(collection_name, config, excel_data, years, page_texts=page_texts)

print("Years:", rag_result["years"])
print("Answers by year:", {y: len(ans) for y, ans in rag_result["answers_by_year"].items()})
print("Context length:", rag_result["context_length"])
print("Retrieval queries:", len(rag_result.get("queries_used", [])))
print("Errors:", rag_result["errors"])


# COMMAND ----------

import re
from rag_poc.retrieve import retrieve_context

# One short, statement-style query per alias (embedding search + cross-encoder rerank work best
# on phrases that look like the line items themselves, not boolean OR lists or instructions).
# Each entry: variable -> (queries to run, keywords to locate the matching line in the context)
YELLOW = {
    "Other Labour Costs": (
        ["Employee benefits expense 2024 2023",
         "Staff costs wages and salaries social security pension costs",
         "Total labour costs consolidated income statement"],
        ["employee benefits", "staff costs", "labour costs", "wages and salaries"],
    ),
    "General Costs": (
        ["Other operating expenses 2024 2023",
         "General and administrative expenses breakdown",
         "Other expenses consolidated income statement"],
        ["other operating expenses", "general and administrative", "administrative expenses", "other expenses"],
    ),
    "Depreciation": (
        ["Depreciation and amortization 2024 2023",
         "Depreciation of property plant and equipment",
         "Depreciation of right-of-use assets"],
        ["depreciation"],
    ),
    "Amortisation": (
        ["Depreciation and amortization 2024 2023",
         "Amortization of intangible assets",
         "Amortisation of capitalised development costs software"],
        ["amortization", "amortisation"],
    ),
    "Interest Received - cash": (
        ["Interest received consolidated statement of cash flows",
         "Interest income 2024 2023",
         "Finance income interest received"],
        ["interest received", "interest income", "finance income"],
    ),
    "Income from Other Finan Assets - cash": (
        ["Income from other financial assets",
         "Income from financial assets cash flow statement",
         "Dividends received financial assets"],
        ["financial assets", "dividends received", "investment income"],
    ),
}

# Financial figures like 61,724 or (46,076) -- excludes note refs such as "24.2" or years
NUM = re.compile(r"\(?\d{1,3}(?:,\d{3})+\)?")

def keyword_hits(text, keywords, window=250, max_hits=3):
    """Return the snippets around keyword matches that contain the most financial figures (table lines)."""
    candidates, low = {}, text.lower()
    for kw in keywords:
        for m in re.finditer(re.escape(kw), low):
            snippet = text[max(0, m.start() - 60): m.end() + window].replace("\n", " ")
            n_figures = len(NUM.findall(text[m.end(): m.end() + 120]))  # figures right after the label
            if n_figures and snippet not in candidates:
                candidates[snippet] = n_figures
    ranked = sorted(candidates, key=candidates.get, reverse=True)
    # drop near-duplicate overlapping windows
    hits = []
    for s in ranked:
        if not any(s[60:140] in h for h in hits):
            hits.append(s)
        if len(hits) >= max_hits:
            break
    return hits

retrieval_check = {}
for variable, (queries, keywords) in YELLOW.items():
    # Merge context from all alias queries, dropping duplicate text
    parts = []
    for q in queries:
        ctx = retrieve_context(collection_name, q, config)
        ctx = ctx if isinstance(ctx, str) else "\n".join(map(str, ctx))
        if ctx and ctx not in parts:
            parts.append(ctx)
    merged = "\n".join(parts)
    hits = keyword_hits(merged, keywords)
    retrieval_check[variable] = {"context_chars": len(merged), "hits": hits}

    print(f"\n=== {variable} ===  (context: {len(merged)} chars, keyword+number hits: {len(hits)})")
    if hits:
        for h in hits:
            print("  ->", h)
    else:
        print("  NO matching line found. First 300 chars:", merged[:300].replace("\n", " ") if merged else "EMPTY")


# COMMAND ----------

import re
import fitz  # PyMuPDF -- same loader the RAG index uses
from rag_poc.extract import METRIC_ALIAS_QUERIES, _norm

# Copy the source PDF locally and extract the text of every page
pdf_abfss = f"abfss://{FOLDER_NAME}@{storage_host}/" + pdf_source.removeprefix(f"{FOLDER_NAME}/")
local_pdf = "/tmp/" + pdf_source.split("/")[-1]
dbutils.fs.cp(pdf_abfss, f"file:{local_pdf}")
doc = fitz.open(local_pdf)
pages = {i + 1: " ".join(doc[i].get_text().split()) for i in range(doc.page_count)}  # 1-based, whitespace collapsed
print(f"PDF pages: {len(pages)}")

NUM_IN_ANSWER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
WORD = re.compile(r"[a-z]{4,}")
STOP = {"total", "other", "cash", "from", "with", "less", "year", "years", "note", "notes", "2024", "2023"}

def value_token(answer):
    """Digits of the answer as printed in the report (sign/parentheses stripped), plus whether it is short."""
    m = NUM_IN_ANSWER.search(str(answer))
    if not m:
        return None, False
    tok = m.group(0)
    short = not ("," in tok or len(tok.replace(".", "")) >= 4)
    return (tok, short) if len(tok.replace(".", "")) >= 2 else (None, False)

# Primary statement each worksheet should cite; a page whose heading (first 300 chars) names it gets a bonus
BALANCE_SHEETS = {"Current_Assets", "Current_Liabilities", "Fixed_and_NonCurrent_Assets", "Long_Term_Liabilities", "Net_Worth"}
def preferred_statement(ws, var):
    if ws in BALANCE_SHEETS:
        return ("statement of financial position", "balance sheet")
    if ws == "Income_Statement" and "- cash" in _norm(var):
        return ("statement of cash flows", "cash flow statement")
    if ws == "Income_Statement":
        return ("statement of comprehensive income", "income statement", "statement of profit or loss")
    return ()
headings = {p: t[:300].lower() for p, t in pages.items()}

def label_words(a):
    """Words that should sit next to the value: label in the model's source_text line, variable name, aliases."""
    words = set(WORD.findall(_norm(a["variable"])))
    for v, spec in METRIC_ALIAS_QUERIES.items():
        if _norm(v) == _norm(a["variable"]):
            for alias in spec["aliases"]:
                words |= set(WORD.findall(alias.lower()))
    tok, _ = value_token(a.get("answer"))
    src = str(a.get("source_text") or "")
    i = src.find(tok) if tok else -1
    if i > 0:  # text immediately before the number in the quoted source = the report's own label
        words |= set(WORD.findall(src[max(0, i - 80): i].lower()))
    return words - STOP

def find_pages(tok, words, other_tok=None, statement=(), short=False):
    """Pages containing the value, scored by: label words just before it, +1 if the other year's value is
    also on the page, +1 if the page is the expected primary statement. Short values (e.g. 310) only count
    when a label word is next to them AND the other year's value is on the same page."""
    pat = re.compile(rf"(?<![\d,.]){re.escape(tok)}(?![\d,]|\.\d)")
    scored = []
    for p, text in pages.items():
        best = None
        for m in pat.finditer(text):
            window = text[max(0, m.start() - 200): m.start()].lower()
            score = sum(w in window for w in words)
            best = score if best is None else max(best, score)
        if best is None:
            continue
        both_years = bool(other_tok) and re.search(rf"(?<![\d,.]){re.escape(other_tok)}(?![\d,])", text) is not None
        if short and not (best >= 1 and both_years):
            continue
        best += int(both_years) + int(any(s in headings[p] for s in statement))
        scored.append((p, best))
    scored.sort(key=lambda x: (-x[1], x[0]))  # highest score first, then earliest page
    return scored

# Index answers by variable for the cross-year check
by_var = {}
for y, ans in rag_result["answers_by_year"].items():
    for a in ans:
        by_var.setdefault((a["worksheet"], a["variable"]), {})[y] = a

rows = []
for (ws, var), per_year in by_var.items():
    for y, a in per_year.items():
        if str(a.get("answer")).strip() in ("N/A", "", "None"):
            continue
        llm_page = a.get("llm_page_number", a.get("page_number"))  # original model page (safe to re-run)
        tok, short = value_token(a.get("answer"))
        other = next((value_token(b.get("answer"))[0] for yy, b in per_year.items() if yy != y), None)
        if ws == "report_metadata":  # text/date fields: a number search is meaningless here
            status, verified, candidates = "metadata (not checked)", llm_page, []
        elif tok is None:
            status, verified, candidates = "not searchable (short/non-numeric value)", llm_page, []
        else:
            scored = find_pages(tok, label_words(a), other, preferred_statement(ws, var), short)
            candidates = [p for p, _ in scored]
            if not scored:
                status, verified = "value not in PDF (derived/computed?)", llm_page
            else:
                verified = scored[0][0]
                status = "confirmed" if verified == llm_page else "corrected"
        a["llm_page_number"] = llm_page
        a["page_number"] = verified
        a["page_candidates"] = candidates[:10]
        a["page_check"] = status
        rows.append({"worksheet": ws, "variable": var.strip(), "year": y, "answer": a.get("answer"),
                     "llm_page": llm_page, "verified_page": verified,
                     "all_pages_with_value": candidates[:10], "status": status})

page_check_df = pd.DataFrame(rows).sort_values(["worksheet", "variable", "year"]).reset_index(drop=True)
print(page_check_df["status"].value_counts().to_string())
display(page_check_df)

# COMMAND ----------

import json
with open("/dbfs/tmp/rag_poc_results.json", "w") as f:
    json.dump(rag_result, f, indent=2, default=str)
print("Saved /dbfs/tmp/rag_poc_results.json")

# COMMAND ----------

import pandas as pd
from template.excel_writer import excel_write

def _safe(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val)

def _safe_list(val):
    if isinstance(val, (list, tuple)):
        return list(val)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    return [str(val)]

years = rag_result["years"]
answers_by_year = rag_result["answers_by_year"]

worksheet_dict = {}
for metric in excel_data:
    worksheet = metric["worksheet"]
    variable = metric["variable"]
    row = {"variable": variable, "Remarks": ""}

    for year in years:
        year_answers = answers_by_year.get(year, [])
        # Match on worksheet AND variable: the same variable name can exist on several worksheets
        match = next((a for a in year_answers
                      if a.get("worksheet") == worksheet and a.get("variable") == variable), {})
        prefix = f"{year}_" if year is not None else ""

        row[f"{prefix}answer"] = match.get("answer", "N/A")
        row[f"{prefix}confidence"] = match.get("confidence", 0.0)
        row[f"{prefix}page_number"] = match.get("page_number", -1)
        row[f"{prefix}source_fields"] = _safe_list(match.get("source_fields"))
        row[f"{prefix}formula"] = _safe(match.get("formula"))
        row[f"{prefix}source_link"] = _safe(match.get("source_link") or "N/A")
        row[f"{prefix}source_heading"] = _safe(match.get("source_heading"))
        row[f"{prefix}source_text"] = _safe(match.get("source_text"))

    worksheet_dict.setdefault(worksheet, []).append(row)

worksheet_dict = {ws: pd.DataFrame(rows) for ws, rows in worksheet_dict.items()}

output_excel = output_path + pdf_file_name.removeprefix("InputData").removesuffix(".pdf") + "_rag_poc.xlsx"
status = excel_write(dataframes=worksheet_dict, output_path=output_excel)
print("Excel written:", status)
