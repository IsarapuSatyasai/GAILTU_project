"""Financial keywords and page-relevance helpers."""

import re
import unicodedata


FINANCIAL_TERMS = [
    "balance sheet",
    "statement of financial position",
    "income statement",
    "statement of profit or loss",
    "statement of profit and loss",
    "profit and loss account",
    "statement of comprehensive income",
    "statement of operations",
    "statement of earnings",
    "cash flow statement",
    "statement of cash flows",
    "statement of changes in equity",
    "consolidated financial statements",
    "notes to the financial statements",
    "notes to consolidated financial statements",
    "total assets",
    "current assets",
    "non current assets",
    "fixed assets",
    "intangible assets",
    "property plant and equipment",
    "trade receivables",
    "accounts receivable",
    "inventories",
    "cash and cash equivalents",
    "total liabilities",
    "current liabilities",
    "non current liabilities",
    "trade payables",
    "accounts payable",
    "borrowings",
    "long term debt",
    "short term debt",
    "lease liabilities",
    "total equity",
    "share capital",
    "retained earnings",
    "revenue",
    "total revenue",
    "net revenue",
    "turnover",
    "sales",
    "net sales",
    "cost of sales",
    "cost of goods sold",
    "gross profit",
    "operating income",
    "operating profit",
    "operating expenses",
    "administrative expenses",
    "finance costs",
    "interest expense",
    "depreciation",
    "amortisation",
    "amortization",
    "profit before tax",
    "profit after tax",
    "net profit",
    "net income",
    "profit for the year",
    "profit for the period",
    "earnings per share",
    "ebit",
    "ebitda",
    "operating activities",
    "investing activities",
    "financing activities",
    "net cash flow",
    "capital expenditure",
    "segment reporting",
    "related party transactions",
    "contingent liabilities",
    "financial instruments",
    "working capital",
    "net debt",
    "total debt",
    "income tax expense",
    "deferred tax",
    "current tax",
    "trade and other receivables",
    "trade and other payables",
    "provisions",
    "goodwill",
    "intangible assets",
    "right of use assets",
    "right-of-use assets",
    "other comprehensive income",
    "dividends",
    "financial liabilities",
    "financial assets",
    "total labor costs",
    "staff costs",
    "employee benefits",
    "personnel expenses",
    "other expenses",
    "other operating expenses",
    "administrative expenses",
    "general and administrative expenses",
    "interest received",
    "interest income",
    "finance income",
    "income from other financial assets",
    "other financial income",
]

STRONG_FINANCIAL_TERMS = [
    "balance sheet",
    "statement of financial position",
    "income statement",
    "statement of profit or loss",
    "statement of profit and loss",
    "statement of comprehensive income",
    "statement of cash flows",
    "cash flow statement",
    "statement of changes in equity",
    "consolidated financial statements",
    "notes to the financial statements",
    "consolidated balance sheet",
    "consolidated income statement",
    "total assets",
    "total liabilities",
    "total equity",
    "profit before tax",
    "profit after tax",
]

UNIT_TERMS = [
    "in thousands",
    "in thousand",
    "in millions",
    "in million",
    "in billions",
    "in billion",
    "thousands of dollars",
    "millions of dollars",
    "thousands of euros",
    "millions of euros",
    "amounts in",
    "figures in",
    "usd",
    "eur",
    "gbp",
    "inr",
    "currency",
    "€",
    "£",
    "$",
]

COMPANY_METADATA_TERMS = [
    "company information",
    "corporate information",
    "company details",
    "corporate details",
    "registered office",
    "registered address",
    "company registration number",
    "registration number",
    "company number",
    "legal entity identifier",
    "principal place of business",
    "reporting entity",
    "corporate identity",
]

AUDITOR_REPORT_TERMS = [
    "independent auditor report",
    "independent auditors report",
    "independent auditor's report",
    "independent auditors' report",
    "report of the independent auditor",
    "report of the auditor",
    "auditor's report",
    "auditors' report",
    "opinion",
    "basis for opinion",
    "responsibilities of the auditor",
    "auditor responsibilities",
    "audit evidence",
    "we have audited",
]

ACCOUNTING_POLICY_TERMS = [
    "significant accounting policies",
    "accounting policies",
    "basis of preparation",
    "basis of consolidation",
    "critical accounting estimates",
    "significant accounting judgements",
    "significant accounting judgments",
]

NOTE_SECTION_TERMS = [
    "notes to the financial statements",
    "notes to consolidated financial statements",
    "notes to the accounts",
    "notes forming part of the financial statements",
    "financial statement notes",
    "consolidated notes",
]

MANAGEMENT_DISCUSSION_TERMS = [
    "management discussion and analysis",
    "management's discussion and analysis",
    "management discussion",
    "operating and financial review",
    "business review",
    "financial review",
    "discussion of financial results",
    "review of financial performance",
    "management report",
    "chairman's statement",
    "chief executive officer's review",
]

LOW_VALUE_SECTION_TERMS = [
    "table of contents",
    "contents",
    "glossary",
    "index",
    "contact us",
    "contact details",
    "corporate directory",
    "management team",
    "notice of meeting",
    "shareholder information",
]

FINANCIAL_SUMMARY_TERMS = [
    "financial highlights",
    "financial summary",
    "financial performance",
    "financial position",
    "five year summary",
    "five-year summary",
    "selected financial information",
]

SECTION_CATEGORY_TERMS = {
    "company_metadata": COMPANY_METADATA_TERMS,
    "auditor_report": AUDITOR_REPORT_TERMS,
    "income_statement": [
        "income statement",
        "statement of profit or loss",
        "statement of profit and loss",
        "profit and loss account",
        "statement of comprehensive income",
        "statement of operations",
        "statement of earnings",
    ],
    "balance_sheet": [
        "balance sheet",
        "statement of financial position",
    ],
    "cash_flow": [
        "cash flow statement",
        "statement of cash flows",
        "statement of cash flow",
    ],
    "changes_in_equity": [
        "statement of changes in equity",
        "statement of changes in shareholders equity",
        "statement of changes in stockholders equity",
    ],
    "accounting_policies": ACCOUNTING_POLICY_TERMS,
    "financial_summary": FINANCIAL_SUMMARY_TERMS,
}

METRIC_SYNONYM_GROUPS = [
    ("revenue", "turnover", "sales"),
    ("total revenue", "total sales", "total turnover"),
    ("net revenue", "net sales"),
    ("cost of sales", "cost of goods sold", "cogs"),
    ("gross profit", "gross income"),
    (
        "operating profit",
        "operating income",
        "profit from operations",
    ),
    (
        "profit before tax",
        "income before tax",
        "earnings before tax",
        "pbt",
    ),
    (
        "profit after tax",
        "net profit after tax",
        "pat",
    ),
    (
        "profit for the year",
        "profit for the period",
        "net income",
    ),
    (
        "cash and cash equivalents",
        "cash equivalents",
    ),
    (
        "trade receivables",
        "accounts receivable",
        "trade debtors",
    ),
    (
        "trade payables",
        "accounts payable",
        "trade creditors",
    ),
    (
        "property plant and equipment",
        "property and equipment",
        "tangible fixed assets",
        "ppe",
    ),
    ("current assets", "short term assets"),
    (
        "non current assets",
        "noncurrent assets",
        "long term assets",
    ),
    ("current liabilities", "short term liabilities"),
    (
        "non current liabilities",
        "noncurrent liabilities",
        "long term liabilities",
    ),
    ("borrowings", "financial borrowings", "loans payable"),
    ("lease liabilities", "lease obligations"),
    (
        "shareholders equity",
        "stockholders equity",
        "shareholders funds",
        "total equity",
    ),
    ("retained earnings", "accumulated profits"),
    (
        "depreciation and amortisation",
        "depreciation and amortization",
    ),
    ("finance costs", "financial costs", "interest expense"),
    (
        "income tax expense",
        "tax expense",
        "taxation expense",
    ),
    (
        "earnings per share",
        "eps",
    ),
    (
        "capital expenditure",
        "capex",
    ),
    (
        "salaries",
        "other labour costs",
        "total labour costs",
        "staff costs",
        "employee benefits",
    ),
    (
        "general costs",
        "other expenses",
        "other operating expenses",
        "administrative expenses",
    ),
    (
        "interest received",
        "interest income",
        "finance income",
    ),
    (
        "income from other finan assets",
        "income from other financial assets",
        "other financial income",
    ),
]

DUTCH_TERMS = [
    "balans",
    "winst en verliesrekening",
    "kasstroomoverzicht",
    "totale activa",
    "totale passiva",
    "eigen vermogen",
    "bedrijfsopbrengsten",
    "nettowinst",
    "financiele positie",
    "financiele resultaten",
]

GERMAN_TERMS = [
    "bilanz",
    "gewinn und verlustrechnung",
    "kapitalflussrechnung",
    "gesamte aktiva",
    "gesamte passiva",
    "eigenkapital",
    "umsatzerlose",
    "jahresuberschuss",
    "finanzlage",
    "finanzergebnis",
]

FRENCH_TERMS = [
    "bilan",
    "compte de resultat",
    "tableau des flux de tresorerie",
    "total de l actif",
    "total du passif",
    "capitaux propres",
    "chiffre d affaires",
    "resultat net",
    "situation financiere",
    "resultat financier",
]

all_keywords = list(
    dict.fromkeys(
        FINANCIAL_TERMS
        + STRONG_FINANCIAL_TERMS
        + UNIT_TERMS
        + DUTCH_TERMS
        + GERMAN_TERMS
        + FRENCH_TERMS
        + [
            term
            for group in METRIC_SYNONYM_GROUPS
            for term in group
        ]
    )
)


def normalize_text(text: str) -> str:
    """Normalize text for case-insensitive phrase matching."""

    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w]+", " ", text)

    return re.sub(r"\s+", " ", text).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    """Return True when a complete phrase occurs in the text."""

    normalized_text = normalize_text(text)
    normalized_phrase = normalize_text(phrase)

    if not normalized_text or not normalized_phrase:
        return False

    pattern = (
        r"(?<!\w)"
        + re.escape(normalized_phrase)
        + r"(?!\w)"
    )

    return re.search(pattern, normalized_text) is not None


def matched_phrases(text: str, phrases: list) -> list:
    """Return the configured phrases found in a text."""

    normalized_text = normalize_text(text)

    return [
        phrase
        for phrase in phrases
        if contains_phrase(normalized_text, phrase)
    ]


def page_score(text: str) -> int:
    """Count distinct financial keyword matches for baseline testing."""

    normalized_text = normalize_text(text)

    return sum(
        contains_phrase(normalized_text, keyword)
        for keyword in all_keywords
    )


def numeric_density(text: str) -> float:
    """Estimate the proportion of numeric values in extracted text."""

    text = str(text)
    tokens = text.split()

    if not tokens:
        return 0.0

    numbers = re.findall(
        r"(?<!\w)\(?[-+]?\d[\d,]*(?:\.\d+)?%?\)?(?!\w)",
        text,
    )

    return min(len(numbers) / len(tokens), 1.0)


def table_structure_score(text: str) -> float:
    """Estimate whether the page contains table-like text."""

    lines = [
        line.strip()
        for line in str(text).splitlines()
        if line.strip()
    ]

    if not lines:
        return 0.0

    numeric_lines = sum(
        len(re.findall(r"\d[\d,.]*", line)) >= 2
        for line in lines
    )

    score = min(
        (numeric_lines / len(lines)) * 2.0,
        2.0,
    )

    if any(
        re.search(r"\s{2,}|\t|\|", line)
        for line in lines
    ):
        score += 1.0

    return min(score, 3.0)


def financial_year_count(text: str) -> int:
    """Count distinct years and financial-year labels."""

    years = set(
        re.findall(r"\b(?:19|20)\d{2}\b", str(text))
    )

    return len(years)


def page_relevance_score(text: str) -> dict:
    """Score financial signals without making a top-N decision."""

    normalized_text = normalize_text(text)

    if not normalized_text:
        return {
            "score": 0.0,
            "keyword_matches": [],
            "strong_matches": [],
            "unit_matches": [],
            "low_value_matches": [],
            "year_count": 0,
            "numeric_density": 0.0,
            "table_structure_score": 0.0,
        }

    keyword_matches = matched_phrases(
        normalized_text,
        all_keywords,
    )
    strong_matches = matched_phrases(
        normalized_text,
        STRONG_FINANCIAL_TERMS,
    )
    unit_matches = matched_phrases(
        normalized_text,
        UNIT_TERMS,
    )
    low_value_matches = matched_phrases(
        normalized_text,
        LOW_VALUE_SECTION_TERMS
        + MANAGEMENT_DISCUSSION_TERMS,
    )

    year_count = financial_year_count(text)
    number_density = numeric_density(text)
    table_score = table_structure_score(text)

    score = (
        min(len(strong_matches) * 3.0, 12.0)
        + min(len(keyword_matches) * 0.8, 10.0)
        + min(len(unit_matches) * 1.0, 4.0)
        + min(year_count * 0.75, 3.0)
        + min(number_density * 30.0, 5.0)
        + table_score
    )

    penalty = min(len(low_value_matches), 3) * 1.0

    if len(normalized_text.split()) < 20:
        penalty += 1.0

    return {
        "score": round(max(score - penalty, 0.0), 2),
        "keyword_matches": keyword_matches,
        "strong_matches": strong_matches,
        "unit_matches": unit_matches,
        "low_value_matches": low_value_matches,
        "year_count": year_count,
        "numeric_density": round(number_density, 4),
        "table_structure_score": round(table_score, 2),
    }