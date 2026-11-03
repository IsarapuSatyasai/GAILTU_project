ltu_europe_financial_analysis_prompts_list = [
    {
        "title": "Financial performance realised and projected",
        "question": """
    Instruction:
    Extract the required fields from the input.
    Also include predefined constant fields exactly as specified.

    Rules:
    - Only extract values for fields that contain placeholders in parentheses.
    - Do NOT infer, modify, or rephrase any constant fields.
    - Always include constant fields in the output exactly as written.

    Output fields:
    Extract the following:
    - Financial analysis of: (Company Name)
    - Qualified or unqualified: (Qualification Status)
    - Consolidated or non-consolidated: (Consolidation Status)

    """,
    },
    {
        "title": "Financial performance realised and projected$Key figures (x EUR mln)",
        "question": """
    Output a single Markdown table with YEARS AS ROWS (never as columns). The first column must be **Year**; all other columns are fixed metric names listed below. Return ONLY the table—no titles, notes, or commentary.

    TABLE STRUCTURE
    - Rows: One row per unique **Year** (4-digit, e.g., 2019, 2020).
    - Columns (in this exact order):
    - Year
    - Net Sales
    - Net Income
    - Gross income %
    - Sustainable EBITDA
    - Sustainable EBITDA %
    - Total Assets
    - NW / Total Assets
    - Net Working Capital
    - Debt/EBITDA
    - Financing Payment
    - Net Cash Income

    ORDERING & DEDUPLICATION
    - List years in chronological order from oldest to latest.
    - If multiple values exist for the same year, use the primary consolidated figure. If still ambiguous, choose the most recent/reliable source for that year.

    MISSING VALUES
    - If any value is not available for a specific year, leave the cell blank.

    UNIT STANDARDIZATION — DISPLAY IN MILLIONS (mln)
    - All monetary amounts must be converted and displayed in **millions** (mln), numeric only (no unit text in the cell).
    - Convert units if the source uses thousands, billions, etc. (e.g., 1,200,000 → 1.2; 2.3B → 2,300).
    - Preserve sign for negatives **except for Financing Payment**, which must always show its **absolute value**.
    - Use standard number formatting without currency symbols.
    - Use comma thousands separators (e.g., 12,345 or 1,234.5).
    - Round to at most one decimal place.
    - Remove trailing zeros and trailing decimal points.

    PERCENTAGES & RATIOS
    - For percentage columns (**Gross income %**, **Sustainable EBITDA %**, **NW / Total Assets**), display values with a **%** sign, rounded to one decimal (e.g., 12.3%).
    - For **Debt/EBITDA**, display as a plain numeric ratio (e.g., 3.2), no units or %.

    STRICT OUTPUT RULES
    - Do NOT create columns for years; years MUST be rows.
    - Do NOT add extra columns or text.
    - Use numeric values only in cells (except the % sign for percentage columns).
    - If the source uses labels like “FY2020” or “2020E”, map to the base year “2020”. If a fiscal year spans two calendar years, use the labeled fiscal year’s terminal year (e.g., FY2020 → 2020).

    TASK
    Populate the extracted values into the Markdown table format described above, ensuring each metric aligns to its respective year, ordered from oldest to latest, leaving blanks where data is unavailable.
    """,
    },
    {
        "title": "Financial performance realised and projected$Profitability",
        "question": """Use ONLY the provided standardized income statement (P&L) figures for the most recent two fiscal years (no external assumptions, no peer benchmarks, no invented causes). If any required P&L anchor line (Revenue/Sales, Operating Profit/EBIT, Net Profit) is missing, state that the assessment is constrained.

    Task: Produce ONE concise, insight-dense paragraph (150–180 words) analyzing profitability across the two most recent fiscal years. Prioritize interpretation and judgment over description. Do NOT provide a line-by-line P&L walkthrough.

    Always include (regardless of materiality ranking):
    - Direction and strength of change in Revenue/Sales, Operating Profit (EBIT), and Net Profit (and note any sign change: profit↔loss).
    - A concluding categorical judgment: “Profitability: Strong/Adequate/Weak; Earnings quality: Strong/Adequate/Weak.”

    Materiality filter (apply before writing additional drivers beyond the anchors, do not make reference to the filter in the output and do not mention items that do not pass the filter):
    - Parameter: TOP_N = 3 (configurable).
    1) Compute year-over-year (YoY) changes for all available P&L line items (e.g., Revenue/Sales, COGS, gross profit, operating expenses, depreciation/amortization, other income/expense, interest, taxes).
    2) Set the anchor profit metric: Net Profit if available; otherwise EBIT.
    3) Rank non-anchor P&L line items by absolute YoY change in their contribution to the anchor profit change.
    4) Select candidates as the TOP_N absolute contributors.
    5) Discuss ONLY candidate items that also pass this threshold test: the item’s absolute YoY change must exceed the absolute YoY change in at least one of: Revenue/Sales, COGS, Operating Expenses (OPEX).
    6) If fewer than TOP_N items pass the threshold test, discuss only those that pass.
    Ignore all other items.

    Tie-break rule (for equal absolute YoY changes or ambiguous ranking):
    Apply the following priority order, highest first:
    (1) Core operating items (COGS, OPEX, gross profit components) over non-operating items,
    (2) Recurring items over “other/one-off” items (e.g., “Other income/expense”),
    (3) Operating items (EBIT/EBITDA-related) over below-the-line items (interest, taxes),
    (4) If still tied, choose the item with the larger absolute level in the most recent year.

    Content requirements (one paragraph, no bullet points):
    - Start with what the movement in Revenue, EBIT, and Net Profit implies about profitability trajectory and resilience (avoid narration).
    - Explain margin dynamics qualitatively (gross and/or operating), focusing on whether cost pressure or operating leverage strengthened or weakened; do not include a ratio breakdown section. Quantify only if essential and keep it minimal.
    - Discuss drivers ONLY for the material items selected by the filter, and ONLY if explicitly supported by the document; otherwise omit driver commentary (no inference or placeholders).
    - Flag profit-quality concerns only if they pass the materiality filter (e.g., profits driven by “other income” vs core operations; unusual interest/tax movement), and state the implication for sustainability.

    Output constraints:
    - Single paragraph only.
    - Use readable number formats when numbers are necessary (k/mln/bln) and prefix currency code (e.g., EUR 100k or EUR 152mln).
    - Avoid long year-by-year numeric strings; if you must quantify, keep to one level + YoY % change OR one delta + YoY %, not multiple comparisons.
    - Do not invent explanations; if the statements do not specify drivers, state the limitation briefly and proceed with judgment based on observed movements.
    """,
    },
    {
        "title": "Financial performance realised and projected$Liquidity / Cash Flow",
        "question": """
    Use ONLY the provided standardized financial statement figures for the most recent two fiscal years (no external assumptions, no industry averages, no invented drivers). If any required cash flow section or Cash & Bank balance is missing, state that the assessment is constrained.

    Task: Write ONE insight-dense paragraph (150–180 words) assessing liquidity and cash flow performance across the two most recent fiscal years. Prioritize interpretation and judgment over description. Do NOT narrate individual cash flow line items.

    Materiality filter (apply before writing, do not make reference to the filter in the output and do not mention items that do not pass the filter):
    - Parameter: TOP_N = 3 (configurable).
    1) Compute year-over-year (YoY) changes for all cash flow line items and for year-end Cash & Bank.
    2) Rank cash flow line items by absolute YoY change.
    3) Select candidates as the TOP_N absolute contributors to the YoY change in total net cash movement.
    4) Discuss ONLY candidate items that also pass this threshold test: the item’s absolute YoY change must exceed the absolute change in at least one of: trade receivables, inventories, trade payables.
    5) If fewer than TOP_N items pass the threshold test, discuss only those that pass.
    Ignore all other items.

    Content requirements (in one paragraph, no bullet points):
    - Compare gross operating cash flow and net cash from operations, explaining what the movement implies about cash generation strength (do not print figures).
    - Mention investing and financing cash flows ONLY for the material items selected by the filter, stating whether they support or pressure liquidity.
    - Explain working-capital impacts (receivables, inventory, payables) as cash tightening/easing and comment on efficiency via cash impact (no DSO/DIO/DPO; quantify only if essential and keep it minimal).
    - State whether operating cash generation covers financing payments, and end with a definitive conclusion on debt service capacity and overall liquidity strength.
    - Note any material change in year-end Cash & Bank and its implication for liquidity.

    Output constraints:
    - Single paragraph only.
    - No ratio breakdowns.
    - No “YYYY: X vs Y” or other year-by-year numeric strings.
    - No parenthetical numeric comparisons.
    - End with a clear categorical judgment: “Debt service capacity: Strong/Adequate/Weak; Liquidity: Strong/Adequate/Weak.
    """,
    },
    {
        "title": "Financial performance realised and projected$Solvency",
        "question": """Use ONLY the provided standardized balance sheet and debt metrics for the most recent two fiscal years (no external assumptions, no peer benchmarks, no invented causes). If any required anchor metric (Risk-bearing capital, Total assets, Long-term interest-bearing debt, Cash & equivalents or debt, EBITDA if debt/EBITDA is provided) is missing, state that the assessment is constrained.

    Task: Produce ONE concise, insight-dense paragraph (150–180 words) analyzing solvency across the two most recent fiscal years. Prioritize interpretation and credit judgment over description. Do NOT provide a line-by-line balance sheet walkthrough.

    Always include (regardless of materiality ranking):
    - Direction of change in risk-bearing capital and in Risk-bearing capital / Total assets, and what that implies for capital adequacy.
    - Direction of change in total assets and whether asset growth (if any) appears debt-funded or capital-funded.
    - Direction of change in long-term interest-bearing debt and in leverage (debt/EBITDA), noting limitations: if EBITDA ≤ 0 or missing, state that debt/EBITDA is not meaningful or constrained.
    - End with a definitive categorical judgment: “Solvency: Strong/Adequate/Weak; Capital quality: Strong/Adequate/Weak.”

    Materiality filter (apply before writing additional drivers beyond the anchors, do not make reference to the filter in the output and do not mention items that do not pass the filter):
    - Parameter: TOP_N = 3 (configurable).
    1) Compute year-over-year (YoY) changes for all available solvency-relevant items (e.g., equity/risk-bearing capital components, total assets, long-term debt, short-term debt if provided, intercompany receivables/debts, intangible assets).
    2) Set the anchor outcome as the change in Risk-bearing capital / Total assets (primary) and the change in debt/EBITDA (secondary, if meaningful).
    3) Rank non-anchor items by absolute YoY change in their contribution to the anchor outcome(s), prioritizing capital adequacy effects over presentation reclassifications.
    4) Select candidates as the TOP_N absolute contributors.
    5) Discuss ONLY candidate items that also pass this threshold test: the item’s absolute YoY change must exceed the absolute YoY change in at least one of: total assets, risk-bearing capital, long-term debt.
    6) If fewer than TOP_N items pass the threshold test, discuss only those that pass.
    Ignore all other items.

    Tie-break rule (for equal absolute YoY changes or ambiguous ranking):
    Apply the following priority order, highest first:
    (1) External capital structure items (equity/risk-bearing capital, interest-bearing debt) over intra-group or non-funding items,
    (2) Interest-bearing debt over non-interest-bearing liabilities,
    (3) Balance-sheet strengthening/weakening drivers (capital injections, debt build/repayment if explicitly shown) over valuation/reclassification lines,
    (4) Items affecting capital quality (intangibles) over neutral items,
    (5) If still tied, choose the item with the larger absolute level in the most recent year.

    Content requirements (one paragraph, no bullet points):
    - Interpret what the movement in capital adequacy and leverage implies for resilience to stress and creditor protection.
    - Discuss intercompany receivables/debts ONLY if material per the filter, stating the structural risk or support implication without speculation.
    - Discuss intangibles ONLY if material per the filter, focusing on capital quality/tangible buffer implications.
    - Mention any anomaly only if material (e.g., sharp leverage increase, equity erosion, meaningful shift to intra-group funding), and link it to solvency risk.
    - Avoid framing asset contractions as 'not debt-funded'; for balance-sheet shrinkage, focus on whether deleveraging, capital depletion, or structural stability is implied by the observed changes.

    Output constraints:
    - Single paragraph only.
    - Use readable number formats when numbers are necessary (k/mln/bln) and prefix currency code (e.g., EUR 100k or EUR 152mln).
    - Avoid long year-by-year numeric strings; if you must quantify, keep to one level + YoY % change OR one delta + YoY %, not multiple comparisons.
    - Do not invent explanations; if the statements do not specify drivers, state the limitation briefly and proceed with judgment based on observed movements.
    - Do not include ratio breakdown sections; only reference the named solvency ratios minimally when essential.
    """,
    },
]
