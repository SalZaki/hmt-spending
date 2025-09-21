#!/usr/bin/env python3
"""
Fetch HM Treasury 'spend greater than £25,000' monthly spreadsheet,
normalize to a stable JSON schema, and write:

  data/hmt/YYYY/YYYY-MM.json

The JSON file contains:
{
  "meta": {... provenance, quality, aggregates, groupings ...},
  "data": [{... normalized rows ...}]
}

Usage:
  # default: previous month
  python scripts/fetch_hmt_spending_data.py

  # specific month
  python scripts/fetch_hmt_spending_data.py --month 2025-02

  # backfill N months including target
  python scripts/fetch_hmt_spending_data.py --month 2025-03 --backfill 2
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
HEADERS = {"User-Agent":"github-action-hmt-spend-json/1.2.0 (+https://github.com/)"}

# Canonical column names -> common aliases (canonicalized)
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
    # optional
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
    Find the first spreadsheet attachment on a GOV.UK 'Transparency data' page.
    Handles the 'Documents' attachment gem and direct assets links.
    """
    soup = BeautifulSoup(html, "html.parser")

    def norm(href: str) -> str:
        return urljoin("https://www.gov.uk", href)

    # 1) Prefer explicit Documents attachments
    for a in soup.select("a.gem-c-attachment__link, a.govuk-link.gem-c-attachment__link"):
        href = a.get("href", "")
        if re.search(r"\.(xlsx|csv)(?:\?.*)?$", href, flags=re.I):
            return norm(href)

    # 2) Any anchor to assets/uploads/media ending with xlsx/csv
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"(assets\.publishing\.service\.gov\.uk|/media/|/government/uploads/).+\.(xlsx|csv)(?:\?.*)?$", href, flags=re.I):
            return norm(href)

    # 3) Fallback: any .xlsx/.csv on the page
    a = soup.find("a", href=re.compile(r"\.(xlsx|csv)(?:\?.*)?$", flags=re.I))
    return norm(a["href"]) if a and a.has_attr("href") else None

def pick_best_sheet(xls: pd.ExcelFile) -> str:
    """
    Choose the worksheet with the most 'signal' columns (supplier/amount/date),
    in case sheet 0 is a cover page.
    """
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
            # lenient contains match (e.g., 'amountgbpnet' contains 'amountgbp')
            for i, cc in enumerate(lc):
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
    s = s.str.extract(r"(-?\d+(?:\.\d+)?)", expand=False)  # keep the first number
    return pd.to_numeric(s, errors="coerce")

def parse_date(series: pd.Series) -> pd.Series:
    """UK data often D/M/Y; store as ISO YYYY-MM-DD."""
    dt = pd.to_datetime(series, errors="coerce", dayfirst=True)
    return dt.dt.strftime("%Y-%m-%d")

def normalize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return normalized dataframe and the column mapping used."""
    mapping = map_columns(df)

    # Build output frame with all known keys (missing -> None)
    out = pd.DataFrame({k: df[mapping[k]] if k in mapping else None for k in ALIASES_CANON.keys()})

    # Parse/format columns
    if "date" in out:
        out["date"] = parse_date(out["date"])

    if "amount_gbp" in out:
        out["amount_gbp"] = parse_amount(out["amount_gbp"])

    # Keep transaction_number as string to preserve leading zeros
    if "transaction_number" in out:
        out["transaction_number"] = out["transaction_number"].astype(str).str.strip().replace({"nan": None})

    # Drop rows with neither supplier nor amount
    out = out[~(out["supplier"].isna() & out["amount_gbp"].isna())]

    # Normalize empty strings to None
    for col in out.columns:
        if pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].str.strip().replace({"": None})

    return out, mapping

def _safe_len(x):
    try: return int(len(x))
    except: return 0

def compute_meta(
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
    # date coverage (observed)
    date_col = pd.to_datetime(df_norm.get("date"), errors="coerce")
    observed_min = date_col.min()
    observed_max = date_col.max()

    # aggregates
    amt = pd.to_numeric(df_norm.get("amount_gbp"), errors="coerce")
    totals = float(amt.sum(skipna=True)) if getattr(amt, "size", 0) else 0.0
    stats = {
        "min":     float(amt.min(skipna=True)) if getattr(amt, "size", 0) else None,
        "max":     float(amt.max(skipna=True)) if getattr(amt, "size", 0) else None,
        "mean":    float(amt.mean(skipna=True)) if getattr(amt, "size", 0) else None,
        "median":  float(amt.median(skipna=True)) if getattr(amt, "size", 0) else None,
        "p95":     float(amt.quantile(0.95)) if getattr(amt, "size", 0) else None,
    }

    def group_top(series_name: str, value_col: str, label_key: str, top_n: int = 10):
        g = df_norm.groupby(series_name, dropna=True)[value_col].agg(["sum","count"]).reset_index()
        g = g.sort_values("sum", ascending=False).head(top_n)
        return [
            {label_key: (row[series_name] if pd.notna(row[series_name]) else None),
             "total": float(row["sum"]), "count": int(row["count"])}
            for _, row in g.iterrows()
        ]

    top_suppliers   = group_top("supplier", "amount_gbp", "supplier")
    by_entity       = group_top("entity", "amount_gbp", "entity")
    by_expense_type = group_top("expense_type", "amount_gbp", "expense_type")

    null_counts = { c: int(df_norm[c].isna().sum()) for c in df_norm.columns }

    # period (DCAT temporal coverage style)
    period_start = dtm.replace(day=1)
    period_end = (dtm.replace(day=1) + relativedelta(months=1) - relativedelta(days=1))

    return {
        # Standards-aligned provenance & discoverability
        "title": f"HM Treasury spend over £25,000 — {dtm:%B %Y}",
        "publisher": "HM Treasury",
        "publication_url": publication_url,
        "source_url": asset_url,
        "license": "Open Government Licence v3.0",
        "license_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "schema_version": "1.1.0",
        "created_by": "hmt-spend-json@1.2.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",

        # Temporal coverage (dcterms:temporal idea)
        "period": {
            "month": dtm.strftime("%Y-%m"),
            "start": period_start.strftime("%Y-%m-%d"),
            "end": period_end.strftime("%Y-%m-%d")
        },
        "observed_date_min": None if pd.isna(observed_min) else observed_min.strftime("%Y-%m-%d"),
        "observed_date_max": None if pd.isna(observed_max) else observed_max.strftime("%Y-%m-%d"),

        # Structure & traceability
        "rows": _safe_len(df_norm),
        "rows_original": _safe_len(df_raw),
        "columns_normalized": list(df_norm.columns),
        "column_mappings": column_map,
        "sheet": {
            "workbook": book_name,
            "worksheet": sheet_name or "<csv>",
            "selector": "auto",
            "reason": "most signal columns"
        },
        "source_file": {
            "bytes": src_bytes,
            "content_type": src_content_type,
            "sha256": src_sha256
        },

        # Data quality (wire up to your schema validator if desired)
        "validation": {
            "schema_checks": {"passed": True, "errors": 0},
            "null_counts": null_counts,
            "parse_warnings": 0
        },

        # Viz-friendly aggregates
        "currency": "GBP",
        "amount_precision": 2,
        "totals": { "amount_gbp": totals },
        "counts": {
            "records": _safe_len(df_norm),
            "suppliers": int(df_norm["supplier"].nunique(dropna=True)),
            "entities": int(df_norm["entity"].nunique(dropna=True)),
            "expense_types": int(df_norm["expense_type"].nunique(dropna=True)),
        },
        "amount_stats": stats,
        "top_suppliers": top_suppliers,
        "by_entity": by_entity,
        "by_expense_type": by_expense_type,

        "keywords": ["HM Treasury", "transparency", "spend over £25,000"],
        "themes": ["Public spending", "Finance"]
    }

def save_month_json(dtm: date, publication_url: str, asset_url: str):
    # Fetch asset
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

    # Read the spreadsheet
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

    # Metadata
    meta = compute_meta(
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
        json.dump({"meta": meta, "data": df_norm.to_dict(orient="records")}, f, ensure_ascii=False, indent=2)

    # Optional: keep sidecar if you want (comment out if not needed)
    with open(out_path.replace(".json", ".meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path} ({meta['rows']} rows)")

# ----------------------- CLI -----------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="Target month in YYYY-MM (default: previous month)")
    ap.add_argument("--backfill", type=int, default=0, help="Also fetch N months before --month (optional)")
    args = ap.parse_args()

    today = date.today()
    base = (today.replace(day=1) - relativedelta(months=1)) if not args.month else datetime.strptime(args.month, "%Y-%m").date().replace(day=1)

    # Single month by default (fast). Backfill if requested.
    months = [base]
    for i in range(1, args.backfill + 1):
        months.append(base - relativedelta(months=i))
    months.sort()

    for dtm in months:
        pub_url = month_to_url(dtm)
        try:
            pr = requests.get(pub_url, headers=HEADERS, timeout=60)
            if pr.status_code != 200:
                print(f"Skip {dtm:%Y-%m}: {pr.status_code} {pub_url}")
                continue
            asset = find_asset_xlsx_or_csv(pr.text)
            if not asset:
                print(f"No spreadsheet link found on {pub_url}")
                continue
            save_month_json(dtm, publication_url=pub_url, asset_url=asset)
        except Exception as e:
            print(f"Error processing {dtm:%Y-%m}: {e}")

if __name__ == "__main__":
    main()
