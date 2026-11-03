"""Collect all metrics for defining user prompt"""

def get_user_prompt(metrics: list) -> str:
    # Prepare Variables List for the Prompt
    variables_to_extract = []
    active_worksheet = ""
    for item in metrics:
        if item["worksheet"] != active_worksheet:
            active_worksheet = item["worksheet"]
            variables_to_extract.append(f"Table: {item['worksheet']}")                                     
        var_req = f"\n- Variable: '{item['variable']}' (Description: {item['description']})"
        variables_to_extract.append(var_req)
        
    variables_list_str = "\n".join(variables_to_extract)
    return variables_list_str