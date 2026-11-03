ltu_european_annual_report_prompts_list = [
    {
        "title": "company name",
        "question": """
        Extract the primary company name from the report below.

        Rules:
        - Return ONLY the company name as a plain string.
        - Do NOT return JSON.
        - Do NOT return explanations, labels, reasoning, or extra text.
        - If multiple companies are mentioned, return the company that is the main subject of the report.
        - Use the company being analyzed, reported on, or discussed as the primary focus of the document.
        - If no company name can be identified with confidence, return: Unknown

        Report:
        {{REPORT_TEXT}}
        """,
    },
    {
        "title": "ESG and Climate and Environmental Risk Assessment$Climate and Environmental Risk Assessment (CERA)",
        "question": """
        Answer the following questions. For each question, display the question first, then provide the answer. Do not use bullet points, numbered lists, tables, or structured lists in your responses. Write in a clear, analytical, and comprehensive style. 
        1. What are the climate and environmental risks identified? Identify ,outline and mention physical, transitional, governmental ,regulatory risks ?  (wildfire, drought, flooding, high emissions etc.)
        2. What are the risk reducing (mitigation and adaptation) measures? Mention measures adopted and initiatives taken (insurance, decarbonization plan, diversification, strategies)
        3. Describe the key challenges and risks facing the company, including climate-related, environmental, market, regulatory, and operational risks. Assess any actual or potential impact on sales, revenues, profitability, cash flow, reserves, operating costs, liabilities, market exposure, foreign exchange (currency) risks, and the company's overall financial position.
        4. List the key strategies, targets, metrics, innovations, collaborations, and recommendations related to climate risk management and mitigation &adaptation.
        """,
    },
    {
        "title": "ESG and Climate and Environmental Risk Assessment$ESG screening$thermal coal checker",
        "question": """
        Objective
        Using only the provided information, determine whether the client derives more than 5% of its total turnover from thermal coal activities.  

        Scope & Definitions 
        -	Thermal coal activities include thermal coal mining, processing, trading, and electricity generation primarily based on thermal coal.
        -	Total Turnover is defined as the consolidated total operating revenue or turnover for the legal entity that is in the application.

        Decision and Output Rules
        Your output must follow this exact format:
        <Insert one of: "Yes", "No"> (Explanation: <Brief explanation citing the specific data used>)
        Interpretation rules:
        "Yes" indicates the client derives more than 5% of its total turnover from thermal coal.
        "No" indicates the client derives less than or equal to 5% of its total turnover from thermal coal.
        If the given document does not contain any information about whether the company has any thermal coal–related revenue, then the answer must be "No".
        """,
    },
    {
        "title": "ESG and Climate and Environmental Risk Assessment$ESG screening$non-conventionals checker",
        "question": """
        Objective 
        Using only the provided information, determine whether the client has operating revenue specifically related to shale gas or other non conventional fossil natural resources that exceeds 5% (upstream) or 20% (midstream or downstream). 
 
        Scope & Definitions: 
        -	Value-chain stage definitions 
            -	Upstream: exploration, development, extraction, or primary production activities or related assets. 
            -	Midstream: processing, trading, transportation, or storage between production and end-market distribution activities or related assets. 
            -	Downstream: refining, marketing, sales, distribution, or other consumer-facing activity or relates assets. 
        -	Non conventional fossil natural resources: Oil & gas derived from tar sands, hydraulic fracturing and shale extraction: shale rock ('shale gas' or 'tight oil'), oil from bituminous sands ('tar sand' oil or'oil sands'), coal bed methane ('coal seam gas') or retorting ('oil shale'). 
        -	Numerator by value chain stage = operating revenue or turnover explicitly attributable to qualifying nonconventional resources at that value chain stage. 
        -	Denominator = Total Turnover, defined as the consolidated total operating revenue or turnover for the legal entity that is in the application.
        -	Calculate the share for each stage separately: upstream share against the >5% threshold; midstream share against the >20% threshold; downstream share against the >20% threshold. 

        Decision and Output Rules:       
        Your output must follow this exact format:
        <Insert one of: "Yes", "No"> (Explanation: The client is classified as <Upstream / Midstream / Downstream> because <short explanation>, its non conventional operating revenue or turnover above the relevant threshold (>5% for upstream; >20% for midstream/downstream) is <Yes/No> because <Brief explanation citing the specific data used>.)
        """,
    },
]

ltu_european_annual_report_agent_prompts_list = [
    {
        "title": "Business description (include Connected Clients)",
        "question": """
        Provide a **concise, business-focused description of the company**.

        ### Required Content
        **Business Model**  
        In a short paragraph, describe the company's business model, including its position in the value chain, core products and/or services, headquarters location, founding year, and legal entity type. Keep this factual and essential.

        **Distinctive Capabilities**  
        In one short paragraph, explain the company's distinctive capabilities relative to its **three most important competitors**, focusing only on material competitive differentiators.

        **Future Resilience**  
        In a concise paragraph, assess the future resilience of the business model, highlighting the most critical market, competitive, technological, or macroeconomic factors affecting sustainability and earnings stability.

        **Porter's Five Forces**  
        Summarize the Porter Five Forces in a **single compact paragraph**. Address each force in **one sentence only**, identifying the main risk exposure, key mitigating factors, and overall impact (low, medium, or high), integrated into continuous prose.

        **SWOT Analysis**  
        Provide a short paragraph covering strengths, weaknesses, opportunities, and threats. Focus only on the most material internal and external factors. No sub-lists or tables.

        **Key Performance Drivers**  
        In a brief paragraph, explain the key operational and strategic drivers of performance. Do **not** repeat information from earlier sections and do **not** restate KPIs.

        **Key Performance Indicators (KPIs)**  
        In one compact paragraph, list and briefly contextualize the most relevant financial and operational KPIs that directly reflect business performance.

        **Key Stakeholder Relationships and Interconnectedness Risk**  
        In a short paragraph, analyze key stakeholder relationships (major clients and suppliers), assess economic interconnectedness or concentration risk (low, medium, or high), and briefly explain mitigation.
        """,
    },
    {
        "title": "Emerging Risks",
        "question": """
        Provide a **concise, company-specific emerging risk assessment** based **solely on information available in the annual report**, while applying structured analytical judgement.

        ### Required Content
        **Risk Identification**  
        Identify the **five most material emerging risks** specific to the company using only the annual report as input. Where risks are not explicitly stated, derive them **logically from disclosed strategy, growth profile, market positioning, and operating model**, but do not introduce external knowledge.  

        Prioritise **forward-looking and business-relevant risks** (e.g., scaling challenges in fast-growing companies), not just control, audit, or compliance risks mentioned by auditors.  

        Present the risks as **five concise structured bullet points**, where each bullet follows this format:
        - **Risk Name:** [short label]  
        - **Risk:** [clear description of the risk]  
        - **Mitigation (if available):** [only if explicitly disclosed or clearly evidenced; otherwise state "Not explicitly disclosed"]
        Collectively, the risks must cover personnel, country/political/geopolitical exposure, technology, supply and labour constraints, environmental factors, and economic cyclicality. Do not include examples here.

        **Risk Examples and Impact**  
        In a focused paragraph, provide **company-specific examples grounded in the annual report** showing how each of the five risks could materialise. Assess the **business impact** of each (low, medium, or high), ensuring impacts are operational or financial and consistent with the company’s disclosed scale and activities. Do not rely on external assumptions.

        **Mitigating Measures**  
        In one concise paragraph, describe the **primary mitigants explicitly mentioned or clearly evidenced in the annual report** for each risk. If mitigation is not clearly disclosed, state this transparently rather than inferring unsupported measures.

        **Geopolitical and Conflict Exposure**  
        In a single integrated paragraph, analyse the impact of **global conflicts and geopolitical tensions** strictly based on the company’s disclosed geographic footprint, supply chain, and market exposure in the annual report. Address both **short-term disruption** and **potential longer-term implications**, but avoid speculation beyond what can reasonably be inferred from the report.

        ### Important Limitation Disclosure  
        Explicitly acknowledge in one sentence that the assessment is **fully dependent on the annual report**, and therefore may **omit material risks not disclosed or insufficiently detailed**, particularly forward-looking, strategic, or rapidly evolving risks (e.g., scaling risks in high-growth companies).
        """,
    },
    {
        "title": "Management, organization and strategy of the company",
        "question": """
        Provide a **concise, company-specific assessment of management, organization, and strategy**.

        ### Required Content
        Organization  
        Explain how the company is organized from an operating perspective, strictly excluding any geographical segmentation. Describe the operating structure only in terms of business units, product lines, or functional divisions. If no operating structure is disclosed or applicable, explicitly state: “There is no operating structure.”  
        Separately, describe the geographical structure of the company, identifying the regions or countries in which it operates and how activities are distributed across them. If no geographical structure is disclosed or applicable, explicitly state: “There is no geographical structure.”  
        Assess whether the organizational chart is clear and whether its level of complexity is proportionate to the company's business model.

        Legal Structure  
        Describe the company's legal structure, including the type of legal entity, ownership structure, and any material regulatory or compliance factors affecting governance or control. Assess whether the legal and organizational setup supports effective oversight or adds structural risk.

        Management and Internal Control  
        Assess how the company is managed and controlled, including whether the Management Information System (MIS) appears sufficient to steer and monitor the business. Identify the key information or metrics used by management, if disclosed, and assess their adequacy for decision-making and control.

        Strategy and Strategic Execution  
        Describe the company's stated strategy and strategic priorities. Assess whether management appears adequately equipped to execute the strategy, taking into account sector-specific and company-specific challenges.

        Key Management Profiles  
        Provide a factual assessment of the CEO and CFO, including names, ages (if disclosed), titles, tenure, educational background, and relevant professional experience. Clearly indicate any recent or announced changes in the CEO or CFO role.

        Governance and Key-Man Risk  
        Where a dominant shareholder or CEO exists, assess whether countervailing powers are in place and whether key-man risk is adequately mitigated through governance structures or management depth.
        """,
    },
    {
        "title": "ESG and Climate and Environmental Risk Assessment$ESG and Sustainability",
        "question": """
        Analyze the Environmental, Social, and Governance (ESG) and Sustainability performance of the company, highlighting its exposure to physical and transition climate risks. Structure the analysis as follows:
        1. **ESG and Climate Risk Overview**
        Provide a one-paragraph company overview that includes industry, geographic footprint, and key operations. ESG commitments, climate specific actions, targets, and reporting frameworks (e.g., TCFD, SASB, GRI). Notable achievements and milestones related to ESG or sustainability and climate specific (e.g., predefined targets met, certifications, awards, strategies, mitigants).

        2. **Environmental and Climate Risks & Initiatives**
        - **Physical Risks**: Vulnerability to acute (e.g., floods, wildfires) and chronic (e.g., sea-level rise, temperature shifts) risks.  
        - **Transition Risks**: Exposure to regulatory changes (e.g., carbon pricing), Policies, market shifts (e.g., demand for low-carbon products), consumer preferences and technological disruptions.  
        - **Environmental Initiatives**: Key programs (e.g., renewable energy adoption, circular economy, biodiversity protection).  
        - **Mitigation Strategies and Adaptation strategies or measures**: Decarbonization plans, water/energy efficiency, supply chain resilience.

        3. **Long-Term Strategy**
        Strategic roadmap for sustainability, ESG integration and Climate risks.  

        4. **Recommendations**
        - Priority actions to reduce physical/transition risk exposure (e.g., diversifying energy sources, enhancing climate adaptation infrastructure). 
        - Opportunities to leverage ESG strengths for competitive advantage.  

        In the response, include each section only when info is there; otherwise, do not mention anything.
        """,
    },
    {
        "title": "ESG and Climate and Environmental Risk Assessment$Climate-related reputational and litigation risks",
        "question": """
        List any known ESG or climate-related reputational or litigation risks facing the company. Include environmental, social, and governance controversies, lawsuits, regulatory investigations, fines, penalties, greenwashing allegations, environmental incidents, or other sustainability-related issues. Describe any actual or potential financial, operational, strategic, or reputational impacts on the business.
        """,
    },
]
