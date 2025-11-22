def safe_float(value):
    """Convert string values like '5,000,000' or '$2M' into float safely."""
    if value is None:
        return 0.0
    try:
        # Remove commas, dollar signs, and whitespace
        cleaned = str(value).replace(",", "").replace("$", "").strip()
        if not cleaned:
            return 0.0
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def safe_divide(numerator, denominator, default=0.0):
    """Safely divide two numbers, returning default if denominator is zero."""
    if denominator == 0 or denominator is None:
        return default
    try:
        return float(numerator) / float(denominator)
    except (ValueError, TypeError, ZeroDivisionError):
        return default


def process_ade_data(ade_json):
    """
    Converts ADE JSON (single or list) into normalized financial data,
    computes key financial metrics, and returns clean JSON-safe results.
    Handles variations in field names and ensures schema correctness.
    """
    if not ade_json:
        print("⚠️ Empty ADE JSON provided.")
        return []

    # 🧠 If ADE JSON is a list (e.g., multiple docs merged), flatten & merge
    if isinstance(ade_json, list):
        merged = {}
        for entry in ade_json:
            if isinstance(entry, dict):
                for k, v in entry.items():
                    merged[k] = v
        ade_json = merged

    # 1️⃣ Normalize all keys (case + aliases)
    normalized = {}
    for k, v in ade_json.items():
        key = k.lower().strip()
        if key in ["totaldebt", "debt"]:
            key = "debt"
        elif key in ["cashflow", "cash_flow"]:
            key = "cash_flow"
        elif key in ["netincome", "net_income"]:
            key = "net_income"
        elif key in ["operatingincome", "operating_income"]:
            key = "operating_income"
        elif key in ["companyname", "name"]:
            key = "company"
        normalized[key] = v

    # 2️⃣ Ensure all required keys exist and convert to floats
    for key in [
        "company", "revenue", "debt", "equity",
        "cash_flow", "net_income", "ebitda", "operating_income"
    ]:
        if key not in normalized:
            normalized[key] = 0 if key != "company" else ""
        elif key != "company":
            normalized[key] = safe_float(normalized[key])
        else:
            # Keep company as string
            normalized[key] = str(normalized[key] or "")

    # 3️⃣ Extract normalized values
    company = normalized["company"]
    revenue = normalized["revenue"]
    debt = normalized["debt"]
    equity = normalized["equity"]
    cash_flow = normalized["cash_flow"]
    net_income = normalized["net_income"]
    ebitda = normalized["ebitda"]
    operating_income = normalized["operating_income"]

    # 4️⃣ Compute derived metrics with safe division
    debt_to_equity = safe_divide(debt, equity)
    debt_to_revenue = safe_divide(debt, revenue)
    net_margin = safe_divide(net_income, revenue)
    return_on_equity = safe_divide(net_income, equity)
    cashflow_to_debt = safe_divide(cash_flow, debt)

    # 5️⃣ Build clean result dictionary
    clean_result = [{
        "company": company,
        "revenue": revenue,
        "debt": debt,
        "equity": equity,
        "cash_flow": cash_flow,
        "net_income": net_income,
        "ebitda": ebitda,
        "operating_income": operating_income,
        "debt_to_equity": debt_to_equity,
        "debt_to_revenue": debt_to_revenue,
        "net_margin": net_margin,
        "return_on_equity": return_on_equity,
        "cashflow_to_debt": cashflow_to_debt,
    }]

    print("✅ Processed ADE data (normalized + computed metrics):", clean_result)
    return clean_result
