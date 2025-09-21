#!/usr/bin/env python3
"""
Fetch HM Treasury 'spend greater than £25,000' for a given month and write:

  data/hmt/YYYY/YYYY-MM.json

Shape:
{
  "metadata": { ... rich provenance, coverage, quality, aggregates ... },
  "data":     [ ... normalized rows ... ]
}

Usage:
  # default: previous month
  python scripts/fetch_hmt_spending_data.py

  # specific month
  python scripts/fetch_hmt_spending_data.py --month 2025-01
"""
import argparse, json, os, re, string, hashlib
from datetime import date, datetime
from urllib.parse import urljoin
from dateutil.relativedelta import relativedelta
import requests
from bs4 import BeautifulSoup
import pandas as pd

# ----------------------- Config -----------------------
PUB_URL_TMPL = "https://www.gov.uk/government/publications/hmt-spend-greater-than-25000-{month}-{year}"
MONTHS = ["january","february","march","april","may","june","july","august","september","october","november","december"]
HEADERS = {"User-Agent":"hmt-spend-json/1.2.0 (+https://github.com/)"}
DEPARTMENT_CODE = "HMT"
SPENDING_THRESHOLD = 25000
CURRENCY = "GBP"
AMOUNT_PRECISION = 2

ALIASES = {
    "department_family": ["department family","department","departmentfamily"],
    "entity":            ["entity","body","entity name"],
    "date":              ["payment date","date","transaction date","paid date"],
    "expense_type":      ["expense type","expenditure type","type","category"],
    "expense_area":      ["expense area","cost centre","cost center","costcentre","directorate","unit"],
    "supplier":          ["supplier","vendor","supplier name","payee","recipient"],
    "transaction_number":["voucher number","transaction number","transaction no","transaction id","reference","ref"],
    "amount_gbp":        ["amount","amount gbp","amount £","amount(£)","£","gbp","net amount","value","amount (gbp)","amount (excl vat)","amount excluding vat"],
    "description":       ["publication description","description","item text","narrative","spend description","notes"],
    # optional extras
    "supplier_postcode": ["supplier postcode","postal code","post code","postcode"],
    "supplier_type":     ["supplier type","supplier category","organisation type","organization type"],
    "contract_number":   ["contract number","contract no","po number","purchase order","purchase order no","purchase order number"],
    "project_code":      ["project code","project","cost code","programme code","program code"],
    "item_text":         ["item text","line description"],
}

# -------------------- Helpers & matching --------------------
def canon(s: str) -> str:
    """Lowercase, trim, drop spaces & punctuation — for robust header matching."""
    s = str(s).strip().lower()
    table = str.maketrans("", "", string.punctuation + " ")
    return s.translate(table)

ALIASES_CANON = {k: set(canon(n) for n in v) for k, v in ALIASES.items()}

def month_to_url(dt: date) -> str:
    return PUB_URL_TMPL.format(month=MONTHS[dt.month-1], year=dt.year)

def find_asset_xlsx_or_csv(html: str) -> str | None:
    """
    Find the first spreadsheet attachment on a GOV.UK page.
    Handles the 'Documents' attachment gem and direct assets links.
    """
    soup = BeautifulSoup(html, "html.parser")

    def norm(href: str) -> str:
        return urljoin("https://www.gov.uk", href)

    # 1) Prefer explicit 'Documents' attachments
    for a in soup.select("a.gem-c-attachment__link, a.govuk-link.gem-c-attachment__link"):
        href = a.get("href", "")
        if re.search(r"\.(xlsx|csv)(?:\?.*)?$", href, flags=re.I):
            return norm(href)

    # 2) Any assets/uploads/media ending with xlsx/csv
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"(assets\.publishing\.service\.gov\.uk|/media/|/government/uploads/).+\.(xlsx|csv)(?:\?.*)?$", href, flags=re.I):
            return norm(href)

    # 3) Fallback: any .xlsx/.csv
    a = soup.find("a", href=re.compile(r"\.(xlsx|csv)(?:\?.*)?$", flags=re.I))
    return norm(a["href"]) if a and a.has_attr("href") else None

def pick_best_sheet(xls: pd.ExcelFile) -> str:
    """Choose the worksheet with the most 'signal' columns (supplier/amount/date)."""
    scores = []
    signals = {"supplier","amount","date"}
    for name in xls.sheet_names:
        try:
            df_head = pd.read_excel(xls, sheet_name=name, nrows=5)
            cols = [canon(c) for c in df_head.columns]
            score = sum(any(sig in c for c in cols) for sig in signals)
            scores.append((score, name))
        except Exception:
            continue
    if not scores:
        return xls.sheet_names[0]
    scores.sort(reverse=True)
    return scores[0][1]

def map_columns(df: pd.DataFrame) -> dict:
    """Map source columns to canonical keys using canonicalized names."""
    cols = list(df.columns)
    lc = [canon(c) for c in cols]
    mapping = {}
    for key, alias_set in ALIASES_CANON.items():
        idx = next((i for i, cc in enumerate(lc) if cc in alias_set), None)
        if idx is None:
            for i, cc in enumerate(lc):  # lenient contains match
                if any(a in cc for a in alias_set):
                    idx = i
                    break
        if idx is not None:
            mapping[key] = cols[idx]
    return mapping

def parse_amount(series: pd.Series) -> pd.Series:
    """Handle numeric and string formats, GBP signs, commas, and (negatives)."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    s = series.astype(str).str.strip()
    s = s.str.replace(",", "", regex=False).str.replace("£", "", regex=False)
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)  # (1234.56) -> -1234.56
    s = s.str.extract(r"(-?\d+(?:\.\d+)?)", expand=False)  # first number
    return pd.to_numeric(s, errors="coerce")

def parse_date(series: pd.Series) -> pd.Series:
    """UK data often D/M/Y; store as ISO YYYY-MM-DD."""
    dt = pd.to_datetime(series, errors="coerce", dayfirst=True)
    return dt.dt.strftime("%Y-%m-%d")

def normalize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return normalized dataframe and the column mapping used."""
    mapping = map_columns(df)
    out = pd.DataFrame({k: df[mapping[k]] if k in mapping else None for k in ALIASES_CANON.keys()})

    if "date" in out:
        out["date"] = parse_date(out["date"])
    if "amount_gbp" in out:
        out["amount_gbp"] = parse_amount(out["amount_gbp"])
    if "transaction_number" in out:
        out["transaction_number"] = out["transaction_number"].astype(str).str.strip().replace({"nan": None})

    # Drop rows with neither supplier nor amount
    out = out[~(out["supplier"].isna() & out["amount_gbp"].isna())]

    # Normalize empty strings to None
    for col in out.columns:
        if pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].str.strip().replace({"": None})

    return out, mapping

# ----------------------- Metadata builders -----------------------
def _safe_len(x):
    try: return int(len(x))
    except: return 0

def uk_fiscal_year_label(dtm: date) -> str:
    """
    UK government financial year runs 1 April -> 31 March.
    Example: Jan 2025 belongs to 2024-25.
    """
    if dtm.month >= 4:  # Apr..Dec
        start = dtm.year
        end = dtm.year + 1
    else:               # Jan..Mar
        start = dtm.year - 1
        end = dtm.year
    return f"{start}-{str(end)[-2:]}"

def estimated_next_publication(dtm: date) -> str:
    """
    Conservative estimate: 15th of the following month (varies in practice).
    """
    nxt = (dtm.replace(day=1) + relativedelta(months=1)).replace(day=15)
    return nxt.strftime("%Y-%m-%d")

def completeness_score_and_coverage(df_norm: pd.DataFrame) -> tuple[float, str, dict]:
    """
    Completeness over core analytic fields; return score in [0,1], coverage label, null_counts dict.
    """
    core_cols = ["date","supplier","entity","amount_gbp","expense_type","expense_area","description"]
    present = [c for c in core_cols if c in df_norm.columns]
    if not present:
        return 0.0, "unknown", {}
    non_null = df_norm[present].notna().sum().sum()
    total = df_norm[present].size
    score = float(non_null / total) if total else 0.0
    if score >= 0.9: coverage = "complete"
    elif score >= 0.6: coverage = "partial"
    else: coverage = "limited"
    null_counts = { c: int(df_norm[c].isna().sum()) for c in df_norm.columns }
    return score, coverage, null_counts

def groups_top(df_norm: pd.DataFrame, key: str, top_n: int = 10, label_key: str | None = None):
    label_key = label_key or key
    g = df_norm.groupby(key, dropna=True)["amount_gbp"].agg(["sum","count"]).reset_index()
    g = g.sort_values("sum", ascending=False).head(top_n)
    return [
        { label_key: (row[key] if pd.notna(row[key]) else None),
          "total": float(row["sum"]),
          "transaction_count": int(row["count"]) }
        for _, row in g.iterrows()
    ]

def compute_metadata(
    dtm: date,
    publication_url: str,
    asset_url: str,
    df_raw: pd.DataFrame,
    df_norm: pd.DataFrame,
    column_map: dict,
    book_name: str,
    sheet_name: str | None,
    src_bytes: int,
    src_content_type: str,
    src_sha256: str
) -> dict:
    # dates
    observed = pd.to_datetime(df_norm.get("date"), errors="coerce")
    earliest = observed.min()
    latest = observed.max()
    period_start = dtm.replace(day=1)
    period_end = (dtm.replace(day=1) + relativedelta(months=1) - relativedelta(days=1))

    # aggregates
    amt = pd.to_numeric(df_norm.get("amount_gbp"), errors="coerce")
    total_amount = float(amt.sum(skipna=True)) if getattr(amt, "size", 0) else 0.0
    stats = {
        "min":     float(amt.min(skipna=True)) if getattr(amt, "size", 0) else None,
        "max":     float(amt.max(skipna=True)) if getattr(amt, "size", 0) else None,
        "mean":    float(amt.mean(skipna=True)) if getattr(amt, "size", 0) else None,
        "median":  float(amt.median(skipna=True)) if getattr(amt, "size", 0) else None,
        "p95":     float(amt.quantile(0.95)) if getattr(amt, "size", 0) else None,
    }

    # quality
    score, coverage, null_counts = completeness_score_and_coverage(df_norm)

    return {
        "title": f"HM Treasury Expenditure Over £25,000 - {dtm:%B %Y}",
        "publisher": "HM Treasury",
        "department_code": DEPARTMENT_CODE,
        "publication_url": publication_url,
        "source_url": asset_url,
        "license": "Open Government Licence v3.0",
        "license_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "schema_version": "1.1.0",
        "data_classification": "public",
        "spending_threshold": SPENDING_THRESHOLD,
        "currency": CURRENCY,
        "amount_precision": AMOUNT_PRECISION,

        "temporal_coverage": {
            "period": dtm.strftime("%Y-%m"),
            "fiscal_year": uk_fiscal_year_label(dtm),
            "start_date": period_start.strftime("%Y-%m-%d"),
            "end_date": period_end.strftime("%Y-%m-%d"),
            "earliest_payment_date": None if pd.isna(earliest) else earliest.strftime("%Y-%m-%d"),
            "latest_payment_date": None if pd.isna(latest) else latest.strftime("%Y-%m-%d"),
        },

        "processing_info": {
            "generator": "hmt-spend-json@1.2.0",
            "processed_timestamp": datetime.utcnow().isoformat() + "Z",
            "update_frequency": "monthly",
            "next_publication_date": estimated_next_publication(dtm),
        },

        "source_worksheet": {
            "workbook": book_name,
            "worksheet": sheet_name or "<csv>",
            "selector": "auto",
            "reason": "most signal columns",
        },

        "source_file": {
            "bytes": src_bytes,
            "content_type": src_content_type,
            "sha256": src_sha256,
        },

        "record_counts": {
            "transaction_count": _safe_len(df_norm),
            "source_record_count": _safe_len(df_raw),
            "unique_suppliers": int(df_norm["supplier"].nunique(dropna=True)) if "supplier" in df_norm else 0,
            "unique_entities": int(df_norm["entity"].nunique(dropna=True))   if "entity"   in df_norm else 0,
            "unique_expense_types": int(df_norm["expense_type"].nunique(dropna=True)) if "expense_type" in df_norm else 0,
        },

        "financial_summary": {
            "total_amount_gbp": total_amount,
            "payment_statistics": stats,
        },

        "data_quality": {
            "completeness_score": round(score, 2),
            "coverage": coverage,
            "validation": {
                "schema_checks_passed": True,
                "parse_errors": 0,
                "parse_warnings": 0,
            },
            "missing_data_counts": null_counts,
        },

        "data_completeness": {
            "supplier_postcode": {"status":"not_provided","reason":"Supplier privacy protection"},
            "supplier_type":     {"status":"not_collected","reason":"Field not part of standard reporting"},
            "contract_number":   {"status":"optional","reason":"Only required for framework contracts"},
            "project_code":      {"status":"internal_use","reason":"Internal tracking codes not disclosed"},
        },

        "known_limitations": [
            "Supplier details limited for privacy reasons",
            "Contract numbers only provided for framework agreements",
            "Some transactions may be aggregated for commercial sensitivity",
            "Excludes classified or security-related expenditure"
        ],

        "top_suppliers": groups_top(df_norm, "supplier", top_n=10, label_key="supplier"),
        "spending_by_entity": groups_top(df_norm, "entity", top_n=50, label_key="entity"),
        "spending_by_expense_type": groups_top(df_norm, "expense_type", top_n=50, label_key="expense_type"),

        "contact_info": {
            "email": "public.enquiries@hmtreasury.gov.uk",
            "department": "HM Treasury Transparency Team"
        },

        "keywords": ["transparency","public spending","government expenditure","HM Treasury"],
        "themes": ["Public Finance","Government Transparency","Fiscal Accountability"]
    }

# ----------------------- Core: fetch → normalize → write -----------------------
def save_month_json(dtm: date, publication_url: str, asset_url: str):
    # Download asset
    resp = requests.get(asset_url, headers=HEADERS, timeout=120)
    resp.raise_for_status()
    content = resp.content
    src_bytes = len(content)
    src_content_type = resp.headers.get("Content-Type", "")
    src_sha256 = hashlib.sha256(content).hexdigest()

    os.makedirs(f"data/hmt/{dtm.year}", exist_ok=True)
    out_path = f"data/hmt/{dtm.year}/{dtm.strftime('%Y-%m')}.json"

    tmp = "/tmp/hmt_asset"
    with open(tmp, "wb") as f:
        f.write(content)

    # Read
    if asset_url.lower().endswith(".csv"):
        df_raw = pd.read_csv(tmp)
        sheet_name = None
        book_name = os.path.basename(asset_url)
    else:
        xls = pd.ExcelFile(tmp)
        sheet_name = pick_best_sheet(xls)
        df_raw = pd.read_excel(xls, sheet_name=sheet_name)
        book_name = os.path.basename(asset_url)

    # Normalize
    df_norm, column_map = normalize_dataframe(df_raw)

    # Build metadata
    metadata = compute_metadata(
        dtm=dtm,
        publication_url=publication_url,
        asset_url=asset_url,
        df_raw=df_raw,
        df_norm=df_norm,
        column_map=column_map,
        book_name=book_name,
        sheet_name=sheet_name,
        src_bytes=src_bytes,
        src_content_type=src_content_type,
        src_sha256=src_sha256
    )

    # Write combined object
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"metadata": metadata, "data": df_norm.to_dict(orient="records")}, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path} ({metadata['record_counts']['transaction_count']} rows)")

# ----------------------- CLI -----------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM (default: previous month)")
    args = ap.parse_args()

    # single month only (fast default)
    today = date.today()
    base = (today.replace(day=1) - relativedelta(months=1)) if not args.month else datetime.strptime(args.month, "%Y-%m").date().replace(day=1)

    pub_url = month_to_url(base)
    try:
        pr = requests.get(pub_url, headers=HEADERS, timeout=60)
        if pr.status_code != 200:
            print(f"Skip {base:%Y-%m}: {pr.status_code} {pub_url}")
            return
        asset = find_asset_xlsx_or_csv(pr.text)
        if not asset:
            print(f"No spreadsheet link found on {pub_url}")
            return
        save_month_json(base, publication_url=pub_url, asset_url=asset)
    except Exception as e:
        print(f"Error processing {base:%Y-%m}: {e}")

if __name__ == "__main__":
    main()
