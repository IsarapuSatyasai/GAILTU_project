import json


def update_responses_with_issue_pages(_dict: dict) -> list:
    """
    Update the response list with a warning when the report contains pages
    that could not be processed.

    The warning is prepended to the responses when the `issued_pages` field
    contains page numbers. These pages may be blank, contain only images,
    or have encountered technical issues during processing and should be
    reviewed manually.

    Args:
        _dict: Dictionary containing a "responses" list. The first response
            is expected to contain an "issued_pages" field with a JSON-encoded
            list of page numbers.

    Returns:
        The updated responses list with a warning inserted at the beginning
        if issued pages exist; otherwise, the original responses list.
    """
    responses = _dict["rag_responses"]
    issue_pages = json.loads(responses[0]["issued_pages"])

    if not issue_pages:
        return responses

    warning = {
        "title": "Warning",
        "answer": (
            "The following pages were not loaded into the system because they "
            "are blank, contain only images, or were affected by technical issues. "
            "You must manually review these pages to ensure that no required "
            f"information has been missed.\n{issue_pages}"
        ),
    }

    responses.insert(0, warning)
    return responses


def update_responses_with_financial_product_catalogue(
    _dict, fpc_local_product_dec_dicts, fpc_product_dec_dict
):
    """
    Appends Financial Product Catalogue (FPC) product and local product descriptions to an existing response list.

    Args:
        _dict (dict): A dictionary containing at least the following keys:
            - 'product_name': The name of the product to retrieve from the local product catalogue.
            - 'country_name': The country associated with the local product.
            - 'rag_responses': A list of existing rag_responses to be updated.
        fpc_local_product_dec_dicts (dict): Country-specific local product
            descriptions indexed by country, product, and local product.
        fpc_product_dec_dict (dict): Product descriptions indexed by
            product name.

    Returns:
        list[dict]: Updated response list with additional FPC records the title hierarchy format:
        "Product and Local Product Description$Product: <name>".

    Note:
        This function assumes the existence of a global dictionary `fpc_local_product_dec_dicts` that maps
        product and country names to their respective financial product catalogue entries.
    """
    country_fpc_product_dec_dict = {}
    country_fpc_local_product_dec_dict = {}

    product_name = _dict["product_name"]
    local_product_name = _dict["local_product_name"]
    country_name = _dict["country_name"]
    updated_responses = _dict["rag_responses"]

    if (local_product_name != "") and (product_name != ""):
        country_fpc_product_dec_dict["title"] = (
            f"Structure analysis & Protection$Product and Local Product Description$Product: {product_name}"
        )
        country_fpc_product_dec_dict["answer"] = fpc_product_dec_dict[product_name]

        updated_responses.append(country_fpc_product_dec_dict)

        country_fpc_local_product_dec_dict["title"] = (
            f"Structure analysis & Protection$Product and Local Product Description$Product: {local_product_name}"
        )
        country_fpc_local_product_dec_dict["answer"] = fpc_local_product_dec_dicts[
            country_name
        ][product_name][local_product_name]

        updated_responses.append(country_fpc_local_product_dec_dict)

    return updated_responses


def update_agent_questions(_dict):
    """
    Return an updated list of agent questions.

    Creates a copy of ``agent_questions`` and, when no
    ``credit_lens_source`` is provided, appends the financial analysis
    questions starting from the third question (index 2). This avoids
    duplicating the first two financial analysis questions, which are
    assumed to be handled separately.

    Args:
        _dict (dict): Input dictionary containing:
            - agent_questions (list[str]): Base agent questions.
            - financial_analysis_questions (list[str]): Financial analysis
              questions to append.
            - credit_lens_source: Indicator of whether Credit Lens data
              is available.

    Returns:
        list[str]: Updated list of agent questions.
    """
    updated_agent_questions = _dict["agent_questions"].copy()

    if not _dict["credit_lens_source"]:
        updated_agent_questions.extend(_dict["financial_analysis_questions"][2:])

    return updated_agent_questions


def build_answers(data, target_titles):
    """
    Extract selected ESG checker results and page references from report data.

    The function searches the provided data for entries whose title matches
    one of the titles specified in ``target_titles``. For each match, it
    creates an output record containing the answer and associated page
    references.

    Args:
        data (list[dict]): A list of report entries. Each entry may contain:
            - title (str): Section title.
            - answer (str): Extracted answer or assessment result.
            - page_no (list[str]): Source page numbers.

        target_titles (set[str] | list[str]): Collection of titles to extract,
            for example:
            {
                "ESG and Climate and Environmental Risk Assessment$ESG screening$non-conventionals checker",
                "ESG and Climate and Environmental Risk Assessment$ESG screening$thermal coal checker",
            }

    Returns:
        dict: A dictionary in the following format:

        {
            "<checker name> result": {
                "result": "<answer text>",
                "Page reference": ["<page1>", "<page2>", ...]
            }
        }
    """
    answers = {}

    for item in data:
        title = item.get("title", "")

        if title in target_titles:
            key = title.split("$")[-1]

            answers[f"{key} result"] = {
                "result": item.get("answer", ""),
                "Page reference": item.get("page_no", []),
            }

    return answers


def update_esg_checkers(_dict, red_list):
    """
    Generate and update ESG checker results in markdown format.

    This function evaluates ESG‑related indicators—such as whether the client's
    country is on the Armaments Red List and whether the client exceeds the
    thermal‑coal turnover threshold. It then compiles these results into a
    three‑column markdown table and inserts it into the
    ESG screening section of `rag_responses`.

    Parameters
    ----------
    _dict : dict
        Input dictionary containing:
        - "rag_responses": nested ESG response structure
        - "country_name": client's country
        - "red_list": list of red‑listed countries
        - any fields required by `build_answers()`

    Returns
    -------
    dict
        The updated `rag_responses` dictionary with an ESG screening table added.
    """
    target_titles = {
        "ESG and Climate and Environmental Risk Assessment$ESG screening$non-conventionals checker",
        "ESG and Climate and Environmental Risk Assessment$ESG screening$thermal coal checker",
    }

    # Remove ESG checker responses that have already been extracted and stored
    # separately in the answers dictionary. This prevents duplicate information
    # from appearing in both the summary output and the remaining responses.
    updated_responses = [
        item
        for item in _dict["rag_responses"]
        if item.get("title") not in target_titles
    ]

    answers = build_answers(
        _dict["rag_responses"],
        target_titles,
    )

    red_list_ind = "No"
    if _dict["country_name"] in red_list:
        red_list_ind = "Yes"

    rows = [
        (
            "Armaments: Red List",
            "Is the client mentioned on Armaments Red list?",
            red_list_ind,  # Yes / No / N/A
            "",
        ),
        (
            "Energy Sector: Thermal coal",
            "Does the client have more than 5% of its turnover from thermal coal?",
            answers["thermal coal checker result"][
                "result"
            ],  # Yes / No / N/A (kept as in your example)
            answers["thermal coal checker result"]["Page reference"],
        ),
        (
            "Energy Sector: Non conventional Fossil Fuels",
            "Does the client have turnover from shale gas or other non-conventional fossil natural resources exceeding 5% (upstream) or 20% (midstream or downstream).",
            answers["non-conventionals checker result"][
                "result"
            ],  # Yes / No / N/A (kept as in your example)
            answers["non-conventionals checker result"]["Page reference"],
        ),
    ]

    # --------------------------
    # Notes above the table
    # --------------------------
    notes = "The following chapter includes the screening outcome with regards to three acceptance requirements, one regarding the Red List (Red List) and two on Energy requirements. Please note that Energy sector screening against acceptance requirements are enabled for all clients. As a user, you must first determine whether the client belongs to the Energy sector (based on the industry code). If the client is in the Energy sector, you must follow the ESG policy (Energy-Policy-Acceptance-Requirements-Guidelines) to either approve or decline the customer. If the customer is not in the Energy sector, the energy sector requirements can be ignored. \n Additional Disclaimer: This assessment is based exclusively on the information contained in the provided document and does not incorporate any external sources, web searches, or supplementary data. Consequently, the findings may be subject to false negatives if relevant information exists outside the document but is not explicitly referenced within it. Users are encouraged to carefully review and validate the results, particularly when they are being used to support important or high-impact decisions.\n"

    # --------------------------
    # Build Markdown header exactly as your example (two lines + separator + section title)
    # --------------------------
    # markdown = (
    #     notes
    #     + "| Screening Parameter | Acceptance requirement | Response (Yes / No / N/A) | Page reference |\n"
    #     "|---|---|---|---|\n"
    # )
    markdown = (
        notes
        + "| Screening Parameter | Acceptance requirement | Response (Yes / No / N/A) | Page reference |\n"
    )

    # --------------------------
    # Append rows to markdown (3 columns)
    # --------------------------
    for desc, question, response, page_reference in rows:
        markdown += f"| {desc} | {question} | {response} | {page_reference}|\n"

    # markdown should be added after "ESG and Climate and Environmental Risk Assessment$Climate and Environmental Risk Assessment (CERA)"
    idx = next(
        i
        for i, item in enumerate(updated_responses)
        if item.get("title")
        == "ESG and Climate and Environmental Risk Assessment$Climate and Environmental Risk Assessment (CERA)"
    )

    updated_responses.insert(
        idx + 1,
        {
            "title": "ESG and Climate and Environmental Risk Assessment$ESG screening",
            "answer": markdown,
        },
    )

    return updated_responses


# def generate_final_response(_dir):
#     """
#     Combines and orders response sections from RAG and agent-generated outputs.

#     The function merges sections from:
#         - `_dir["rag_responses"]` (RAG-generated responses)
#         - `_dir["agent_responses"]` (agent-generated responses)

#     Both inputs are expected to be lists of dictionaries in the format:
#         [
#             {
#                 "title": "<section title>",
#                 "answer": "<section content>"
#             },
#             ...
#         ]

#     The merged list is ordered according to the predefined `order` list.
#     Sections whose titles are not present in `order` are placed after all
#     ordered sections while preserving their relative order.

#     Args:
#         _dir (dict): Dictionary containing:
#             - responses (list[dict]): RAG-generated response sections.
#             - agent_responses (list[dict]): Agent-generated response sections.

#     Returns:
#         list[dict]: Combined and ordered list of response sections.

#     """
#     order = [
#         "Warning",
#         "Business Description",
#         "Emerging Risks",
#         "ESG and Climate and Environmental Risk Assessment$ESG and Sustainability",
#         "ESG and Climate and Environmental Risk Assessment$Climate and Environmental Risk Assessment (CERA)",
#         "ESG and Climate and Environmental Risk Assessment$Climate-related reputational and litigation risks",
#         "ESG and Climate and Environmental Risk Assessment$Climate and Environmental Risk Assessment (CERA)$ESG screening",
#         "Management Organization Strategy",
#         "Financial performance realised and projected$Revenue and Profitability Analysis",
#         "Financial performance realised and projected$Revenue and Profitability Analysis from the notes",
#         "Financial performance realised and projected$Cash Flows Analysis",
#         "Financial performance realised and projected$Cash Flows Analysis from the notes",
#         "Financial performance realised and projected$Solvency Analysis from the notes",
#         "Financial performance realised and projected$Auditor’s Report",
#     ]

#     rag_responses = _dir["rag_responses"]
#     agent_responses = _dir["agent_responses"]

#     combined = rag_responses + agent_responses

#     order_map = {title: idx for idx, title in enumerate(order)}

#     final_response = sorted(
#         combined, key=lambda item: order_map.get(item["title"], len(order))
#     )

#     return final_response
