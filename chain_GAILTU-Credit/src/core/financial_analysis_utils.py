import re


def generate_final_response(_dir):
    """
    Generate the final ordered response.

    CreditLens responses are used as the base output. If annual report
    responses are available, the CreditLens sections "Profitability",
    "Liquidity / Cash Flow", and "Solvency" are removed and replaced by the
    corresponding annual report sections.

    The resulting responses are ordered according to:
    General, Key figures, Profitability, Liquidity / Cash Flow, Solvency.

    Args:
        _dir (dict): Dictionary containing:
            - credit_lens_chain_responses (list[dict])
            - additional_report_chain_responses (list[dict] | None)

    Returns:
        list[dict]: Final ordered response sections.
    """
    order = [
        "Financial performance realised and projected",
        "Financial performance realised and projected$Key figures (x EUR mln)",
        "Financial performance realised and projected$Profitability",
        "Financial performance realised and projected$Liquidity / Cash Flow",
        "Financial performance realised and projected$Solvency",
    ]

    credit_lens_responses = _dir["credit_lens_chain_responses"]
    annual_report_responses = _dir.get("additional_report_chain_responses") or []

    if annual_report_responses:
        replace_titles = {
            "Financial performance realised and projected$Profitability",
            "Financial performance realised and projected$Liquidity / Cash Flow",
            "Financial performance realised and projected$Solvency",
        }

        credit_lens_responses = [
            item
            for item in credit_lens_responses
            if item["title"] not in replace_titles
        ]

    combined = credit_lens_responses + annual_report_responses

    order_map = {title: idx for idx, title in enumerate(order)}

    final_response = sorted(
        combined, key=lambda item: order_map.get(item["title"], len(order))
    )

    return final_response


def clean_conversion_block(contexts):
    """
    Cleans up 'Conversion Rate' blocks from a list of context dictionaries.

    Each context is expected to be a dictionary with a 'text' key.
    If the text contains the phrase 'Conversion Rate', this function removes
    the entire block starting from 'Conversion Rate' followed by any number
    of decimal numbers (e.g., 0.56818), up to the next non-numeric, non-whitespace character.

    Parameters:
        contexts (list of dict): A list of dictionaries, each containing a 'text' field.

    Returns:
        list of dict: The modified list with 'Conversion Rate' blocks removed where applicable.
    """
    cleaned_contexts = []

    for context in contexts:
        text = context["text"]

        # Check if 'Conversion Rate' is in the text
        if "Conversion Rate" in text:
            # Regex pattern to match 'Conversion Rate' followed by optional decimal numbers
            pattern = r"Conversion Rate\s*(?:\d+\.\d+\s*)*?(?=[^\s\d.]|$)"
            # Remove the matched pattern from the text
            result = re.sub(pattern, "", text, flags=re.DOTALL)
            context["text"] = result

        # Add the cleaned or unchanged context to the result list
        cleaned_contexts.append(context)

    return cleaned_contexts


def remove_currency_block(contexts):
    """
    Removes blocks of text starting with the line "Currency" and ending just before a line starting with "Restated"
    from the "text" field of each dictionary in the input list.

    Args:
        contexts (list of dict): A list of dictionaries, each containing a "text" key with a string value.

    Returns:
        list of dict: A list of dictionaries with the "Currency" blocks removed from the "text" field.
    """

    cleaned_contexts = []

    for context in contexts:
        text = context["text"]

        lines = text.split("\n")
        output_lines = []
        skip = False

        for line in lines:
            if line.strip().startswith("Currency"):
                skip = True
            elif line.strip().startswith("Restated"):
                skip = False
                output_lines.append(line)
            elif not skip:
                output_lines.append(line)

        context["text"] = "\n".join(output_lines)

        cleaned_contexts.append(context)

    return cleaned_contexts
