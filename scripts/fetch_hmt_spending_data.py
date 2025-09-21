#!/usr/bin/env python3
import argparse, json, os, re, string
from datetime import date, datetime
from urllib.parse import urljoin
from dateutil.relativedelta import relativedelta
import requests
from bs4 import BeautifulSoup
import pandas as pd

PUB_URL_TMPL = "https://www.gov.uk/government/publications/hmt-spend-greater-than-25000-{month}-{year}"
MONTHS = ["january","february","march","april","may","june","july","august","september","october","november","december"]
HEADERS = {"User-Agent":"github-action-hmt-spend-json/1.0 (+https://github.com/)"}

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
    "supplier_type":     ["supplier type","supplier category","organisation type"],
    "contract_number":   ["contract number","contract no","po number","purchase order","purchase order no","purchase order number"],
    "project_code":      ["project code","project","cost code","programme code"],
    "item_text":         ["item text","line description"],
}

# ---------- Helpers ----------
def canon(s: str) -> str:
    s = str(s).strip().lower()
    # remove punctuation and spaces (keep letters/numbers)
    table = str.maketrans("", "", string.punctuation + " ")
    return s.translate(table)

def build_alias_map():
    m = {}
    for k, names in ALIASES.items():
        m[k] = set(canon(n) for n in names)
    return m

ALIASES_CANON = build_alias_map()

def month_to_url(dt: date) -> str:
    return PUB_URL_TMPL.format(month=MONTHS[dt.month-1], year=dt.year)

def find_asset_xlsx_or_csv(html: str) -> str | None:
    """Find first spreadsheet attachment on the GOV.UK page."""
    soup = BeautifulSoup(html, "html.parser")

    def norm(href: str) -> str:
        return urljoin("https://www.gov.uk", href)

    # 1) Prefer explicit 'Documents' attachments
    for a in soup.select("a.gem-c-attachment__link, a.govuk-link.gem-c-attachment__link"):
        href = a.get("href", "")
        if re.search(r"\.(xlsx|csv)(?:\?.*)?$", href, flags=re.I):
            return norm(href)

    # 2) Any anchor to assets/uploads/media ending with xlsx/csv
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"(assets\.publishing\.service\.gov\.uk|/media/|/government/uploads/).+\.(xlsx|csv)(?:\?.*)?$", href, flags=re.I):
            return norm(href)

    # 3) Fallback: any .xlsx/.csv
    a = soup.find("a", href=re.compile(r"\.(xlsx|csv)(?:\?.*)?$", flags=re.I))
    return norm(a["href"]) if a and a.has_attr("href") else None

def pick_best_sheet(xls: pd.ExcelFile) -> str:
    """
    Choose the sheet with the most 'signal' columns (supplier/amount/date).
    """
    scores = []
    signal = {"supplier","amount","date"}
    for name in xls.sheet_names:
        try:
            # Read just header row to inspect
            df_head = pd.read_excel(xls, sheet_name=name, nrows=5)
            cols = [canon(c) for c in df_head.columns]
            score = sum(any(sig in c for c in cols) for sig in signal)
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
        match_idx = None
        # exact canonical match
        for i, cc in enumerate(lc):
            if cc in alias_set:
                match_idx = i
                break
        # lenient contains (e.g., 'amountgbp' found inside 'amountgbpnet')
        if match_idx is None:
            for i, cc in enumerate(lc):
                if any(a in cc for a in alias_set):
                    match_idx = i
                    break
        if match_idx is not None:
            mapping[key] = cols[match_idx]
    return mapping

def parse_amount(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    s = series.astype(str).str.strip()
    s = s.str.replace(",", "", regex=False).str.replace("£", "", regex=False)
    # parentheses for negatives e.g. (1234.56)
    neg = s.str.match(r"^\(.*\)$", na=False)
    s = s.str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    # keep only first number
    s = s.str.extract(r"(-?\d+(?:\.\d+)?)", expand=False)
    out = pd.to_numeric(s, errors="coerce")
    # 'neg' already applied by replacement; keep line for clarity
    return out

def parse_date(series: pd.Series) -> pd.Series:
    # UK data commonly uses day-first; coerce invalids to NaT, then to str
    dt = pd.to_datetime(series, errors="coerce", dayfirst=True)
    return dt.dt.strftime("%Y-%m-%d")

def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    mapping = map_columns(df)

    # Build output frame with all known keys, fill missing with None
    out = pd.DataFrame({k: df[mapping[k]] if k in mapping else None for k in ALIASES_CANON.keys()})

    # Parse/format columns
    if "date" in out:
        out["date"] = parse_date(out["date"])

    if "amount_gbp" in out:
        out["amount_gbp"] = parse_amount(out["amount_gbp"])

    # Make transaction_number a string (preserve leading zeros)
    if "transaction_number" in out:
        out["transaction_number"] = out["transaction_number"].astype(str).str.strip().replace({"nan": None})

    # Drop rows with neither supplier nor amount
    out = out[~(out["supplier"].isna() & out["amount_gbp"].isna())]

    # Optional: trim empty strings to None
    for col in out.columns:
        if pd.api.types.is_string_dtype(out[col]):
            out[col] = out[col].str.strip().replace({"": None})

    return out

def save_month_json(dt: date, asset_url: str):
    os.makedirs(f"data/hmt/{dt.year}", exist_ok=True)
    out_path = f"data/hmt/{dt.year}/{dt.strftime('%Y-%m')}.json"

    r = requests.get(asset_url, headers=HEADERS, timeout=120)
    r.raise_for_status()
    tmp = "/tmp/hmt_asset"
    with open(tmp, "wb") as f:
        f.write(r.content)

    # Read spreadsheet
    if asset_url.lower().endswith(".csv"):
        df = pd.read_csv(tmp)
    else:
        xls = pd.ExcelFile(tmp)
        sheet = pick_best_sheet(xls)
        df = pd.read_excel(xls, sheet_name=sheet)

    norm = normalize_dataframe(df)

    meta = {
        "source": asset_url,
        "publisher": "HM Treasury",
        "license": "Open Government Licence v3.0",
        "generated_at": datetime.utcnow().isoformat()+"Z",
        "rows": int(len(norm)),
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(norm.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    with open(out_path.replace(".json",".meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Wrote {out_path} ({meta['rows']} rows)")

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="Target month in YYYY-MM (default: previous month)")
    ap.add_argument("--backfill", type=int, default=0, help="Also fetch N months before --month (optional)")
    args = ap.parse_args()

    today = date.today()
    base = (today.replace(day=1) - relativedelta(months=1)) if not args.month else datetime.strptime(args.month, "%Y-%m").date().replace(day=1)

    months = [base]
    for i in range(1, args.backfill+1):
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
            save_month_json(dtm, asset)
        except Exception as e:
            print(f"Error processing {dtm:%Y-%m}: {e}")

if __name__ == "__main__":
    main()
