#!/usr/bin/env python3
"""
fetch_edgar.py — SEC EDGAR Form 4 insider trades and XBRL financials.
Usage: python3 scripts/fetch_edgar.py <SYMBOL>
Output: JSON to stdout
Free API — no key required.
"""

import re
import sys
import json
import datetime
import requests

BASE = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
COMPANY_FACTS_BASE = "https://data.sec.gov/api/xbrl/companyfacts"

HEADERS = {
    "User-Agent": "trading-ops/1.0 research@example.com",
    "Accept": "application/json",
}


def find_cik(symbol):
    resp = requests.get(
        "https://efts.sec.gov/LATEST/search-index",
        params={"q": f'"{symbol}"', "dateRange": "custom", "startdt": "2020-01-01", "forms": "10-K"},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])
    for hit in hits:
        src = hit.get("_source", {})
        cik = src.get("file_num", "") or hit.get("_id", "").split(":")[0]
        tickers = src.get("tickers", []) or []
        if symbol.upper() in [t.upper() for t in tickers]:
            return src.get("cik", cik)

    resp2 = requests.get(
        "https://www.sec.gov/cgi-bin/browse-edgar",
        params={"company": symbol, "CIK": symbol, "type": "10-K", "dateb": "", "owner": "include", "count": "5", "search_text": "", "action": "getcompany", "output": "atom"},
        headers=HEADERS,
        timeout=15,
    )
    if resp2.status_code == 200:
        match = re.search(r'CIK=(\d+)', resp2.text)
        if match:
            return match.group(1).lstrip("0")
    return None


def fetch_form4_filings(cik, days=90):
    padded_cik = str(cik).zfill(10)
    resp = requests.get(
        f"{SUBMISSIONS_BASE}/CIK{padded_cik}.json",
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    form4_filings = []
    for form, date_str, acc in zip(forms, dates, accessions):
        if form == "4" and date_str:
            try:
                filing_date = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d")
                if filing_date >= cutoff:
                    form4_filings.append({
                        "form": form,
                        "date": date_str[:10],
                        "accession": acc,
                    })
            except ValueError:
                continue

    return form4_filings


def fetch_xbrl_financials(cik):
    padded_cik = str(cik).zfill(10)
    resp = requests.get(
        f"{COMPANY_FACTS_BASE}/CIK{padded_cik}.json",
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    facts = resp.json()

    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    def latest_annual(concept):
        data = us_gaap.get(concept, {}).get("units", {}).get("USD", [])
        annual = [d for d in data if d.get("form") in ("10-K", "10-K/A") and d.get("val") is not None]
        if not annual:
            return None
        annual.sort(key=lambda x: x.get("end", ""), reverse=True)
        return annual[0].get("val")

    revenues = latest_annual("Revenues") or latest_annual("RevenueFromContractWithCustomerExcludingAssessedTax")
    net_income = latest_annual("NetIncomeLoss")
    operating_cf = latest_annual("NetCashProvidedByUsedInOperatingActivities")
    total_debt = latest_annual("LongTermDebt") or latest_annual("LongTermDebtCurrent")
    total_assets = latest_annual("Assets")

    return {
        "revenue_latest": revenues,
        "net_income_latest": net_income,
        "operating_cash_flow_latest": operating_cf,
        "total_debt_latest": total_debt,
        "total_assets_latest": total_assets,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python3 fetch_edgar.py <SYMBOL>"}))
        sys.exit(1)

    symbol = sys.argv[1].strip().upper()
    output = {
        "symbol": symbol,
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "errors": [],
    }

    cik = None
    try:
        cik = find_cik(symbol)
        if not cik:
            output["errors"].append(f"CIK not found for symbol '{symbol}'. Check ticker or use full company name.")
            output["cik"] = None
            output["insider_activity"] = {"form4_count_last_90d": 0, "filings": []}
            output["financials"] = {}
            print(json.dumps(output, indent=2, default=str))
            return
        output["cik"] = cik
    except Exception as e:
        output["errors"].append(f"CIK lookup failed: {str(e)}")
        output["cik"] = None

    if cik:
        try:
            filings = fetch_form4_filings(cik, days=90)
            output["insider_activity"] = {
                "form4_count_last_90d": len(filings),
                "filings": filings[:10],
            }
        except Exception as e:
            output["errors"].append(f"Form 4 fetch failed: {str(e)}")
            output["insider_activity"] = {"form4_count_last_90d": 0, "filings": []}

        try:
            financials = fetch_xbrl_financials(cik)
            output["financials"] = financials
        except Exception as e:
            output["errors"].append(f"XBRL financials failed: {str(e)}")
            output["financials"] = {}

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
