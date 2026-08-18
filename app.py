"""
Uncle's IPO & Stock Prospectus Finder
-------------------------------------
A read-only research dashboard for recent SEC Form S-1 filings.
This app does not trade, connect to a brokerage, or give investment advice.

Run locally:
    python -m pip install -r requirements.txt
    python -m streamlit run app.py
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import streamlit as st

APP_TITLE = "Uncle's IPO & Stock Prospectus Finder"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
REQUEST_TIMEOUT = 20
SNAPSHOT_PATH = Path(__file__).resolve().parent / "data" / "latest_filings.json"
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)

SIC_LABELS = {
    "1000": "Metal mining",
    "1040": "Gold & silver ores",
    "1311": "Oil & gas",
    "2080": "Beverages",
    "2833": "Medicinal chemicals",
    "2834": "Drug companies",
    "2836": "Biotech / biologics",
    "3571": "Computers",
    "3674": "Chips / semiconductors",
    "3711": "Cars",
    "3812": "Navigation equipment",
    "3841": "Medical devices",
    "4899": "Communications",
    "6022": "Banks",
    "6199": "Finance / crypto-adjacent",
    "6221": "Commodity brokers",
    "6770": "Blank-check / SPAC shells",
    "7370": "Computer services",
    "7371": "Programming services",
    "7372": "Software",
    "7374": "Data processing",
    "7389": "Business services",
}

KIND_FILTERS = {
    "Everything on the desk": None,
    "Possible new offerings": "possible_ipo",
    "Already has a ticker": "already_public",
    "Blank-check SPACs": "spac",
    "My watchlist": "watchlist",
}

CHECKLIST_ITEMS = [
    {
        "key": "proceeds",
        "title": "Where does the money go?",
        "prompt": "Find “Use of Proceeds.” Are they building a business, or paying insiders and old debt?",
    },
    {
        "key": "profit",
        "title": "Do they make money yet?",
        "prompt": "Many S-1 companies have never been profitable. That is not automatically bad — but it is not a shortcut to riches either.",
    },
    {
        "key": "lockup",
        "title": "When can insiders sell?",
        "prompt": "Look for the lock-up (often 90–180 days). When it ends, a lot of shares can hit the market at once.",
    },
]


def inject_css() -> None:
    st.markdown(
        """
        <style>
          @import url("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@600;700&display=swap");

          html, body, [class*="css"]  {
            font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
            font-size: 17px;
          }

          .stApp {
            background:
              radial-gradient(1200px 500px at 10% -10%, rgba(232, 197, 71, 0.08), transparent 55%),
              radial-gradient(900px 400px at 100% 0%, rgba(78, 205, 196, 0.06), transparent 50%),
              #0B1020;
          }

          h1, h2, h3, .app-kicker {
            font-family: "IBM Plex Serif", Georgia, serif;
          }

          .app-kicker {
            color: #E8C547;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            font-size: 0.78rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
          }

          .app-subtitle {
            color: #C5CCDC;
            font-size: 1.12rem;
            line-height: 1.6;
            max-width: 48rem;
            margin-bottom: 1.1rem;
          }

          div[data-testid="stAlert"] {
            border: 1px solid #3A4668;
            border-radius: 12px;
          }

          div[data-testid="stMetric"] {
            background: #141A2E;
            border: 1px solid #2A3554;
            border-radius: 14px;
            padding: 0.85rem 1rem;
          }

          div[data-testid="stMetricValue"] {
            font-variant-numeric: tabular-nums;
          }

          .filing-chip {
            display: inline-block;
            border-radius: 999px;
            padding: 0.18rem 0.7rem;
            font-size: 0.78rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            margin-right: 0.4rem;
            margin-bottom: 0.4rem;
          }

          .chip-s1 { background: #1F3D32; color: #7EE0C6; }
          .chip-amend { background: #3A2A14; color: #E8C547; }
          .chip-spac { background: #3A2230; color: #F4A5C0; }
          .chip-ipo { background: #1A3348; color: #9BD4FF; }
          .chip-public { background: #2A2F24; color: #D7E0A8; }
          .chip-today { background: #E8C547; color: #1B1403; }
          .chip-muted { background: #1C243C; color: #C5CCDC; }

          .buy-box {
            background: #1C243C;
            border-left: 4px solid #E8C547;
            border-radius: 10px;
            padding: 0.75rem 0.9rem;
            color: #F2F0E9;
            margin: 0.4rem 0 0.9rem;
            line-height: 1.5;
          }

          .hype-track, .reality-track {
            height: 10px;
            border-radius: 999px;
            background: #1C243C;
            overflow: hidden;
            margin: 0.35rem 0 0.85rem;
          }

          .hype-fill { height: 100%; background: linear-gradient(90deg, #F4A261, #E76F51); }
          .reality-fill { height: 100%; background: linear-gradient(90deg, #2A9D8F, #4ECDC4); }

          .meter-label {
            font-size: 0.82rem;
            color: #A8B0C4;
            display: flex;
            justify-content: space-between;
          }

          .fine-print { color: #8B93A7; font-size: 0.9rem; line-height: 1.55; }
          a, a:visited { color: #E8C547; }
          a:hover { color: #F3D97A; }
          .block-container { padding-top: 1.4rem; padding-bottom: 3rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def looks_like_sec_user_agent(value: str) -> tuple[bool, str]:
    text = (value or "").strip()
    if not text:
        return False, "The SEC wants a name plus an email, for example: Dan Research dan@example.com"
    email_match = EMAIL_RE.search(text)
    if not email_match:
        return False, "Add a contact email to the User-Agent so the SEC can reach you if needed."
    name_part = (text[: email_match.start()] + text[email_match.end() :]).strip(" ,;-")
    if len(name_part) < 2:
        return False, "Add a short name before the email. Example: Dan Research dan@example.com"
    if text.lower() in {"python-requests", "curl", "wget"} or text.lower().startswith("mozilla/"):
        return False, "Use a real name and email, not a browser default."
    return True, ""


def secret_user_agent() -> str:
    env_value = os.environ.get("SEC_USER_AGENT", "").strip()
    if env_value:
        return env_value
    try:
        return str(st.secrets["sec"]["user_agent"]).strip()
    except Exception:
        return ""


def parse_display_name(raw: str) -> tuple[str, str | None]:
    name = raw.split(" (")[0].strip() or raw
    ticker = None
    for group in re.findall(r"\(([^)]+)\)", raw):
        if group.upper().startswith("CIK"):
            continue
        ticker = group.split(",")[0].strip() or None
        break
    return name, ticker


def industry_label(sic: str | None) -> str:
    if not sic:
        return "Unclassified"
    return SIC_LABELS.get(sic, f"Industry code {sic}")


def document_urls(cik: str, accession: str, primary_document: str) -> tuple[str, str]:
    cik_int = str(int(cik)) if cik.isdigit() else cik.lstrip("0") or "0"
    accession_plain = accession.replace("-", "")
    doc = quote(primary_document)
    prospectus = f"{ARCHIVES_BASE}/{cik_int}/{accession_plain}/{doc}"
    index_page = f"{ARCHIVES_BASE}/{cik_int}/{accession_plain}/{accession}-index.html"
    return prospectus, index_page


def is_spac(company: str, sic: str | None) -> bool:
    lowered = company.lower()
    if sic == "6770":
        return True
    spac_words = ("acquisition", "blank check", "spac")
    entity_words = ("corp", "company", "inc", "ltd", "limited", "partners")
    return any(word in lowered for word in spac_words) and any(word in lowered for word in entity_words)


def classify_kind(company: str, ticker: str | None, sic: str | None) -> dict[str, str]:
    if is_spac(company, sic):
        return {
            "kind": "spac",
            "kind_label": "Blank-check / SPAC",
            "buy_answer": "No. This is usually an empty shell looking for a company to buy later. It can look like a new stock offering, but it is not a normal business going public.",
        }
    if ticker:
        return {
            "kind": "already_public",
            "kind_label": "May already trade",
            "buy_answer": "Probably not a brand-new IPO. Companies that already have a ticker often file an S-1 to sell extra shares or let insiders resell. That is paperwork, not a secret listing.",
        }
    return {
        "kind": "possible_ipo",
        "kind_label": "Possible new offering",
        "buy_answer": "Not yet. An S-1 means they told the SEC they might offer stock. There is no Buy button here, and retail investors usually cannot get a special cheap price.",
    }


def mock_hype_reality(name: str, sic: str | None, form_type: str, kind: str) -> tuple[int, int, str]:
    if kind == "spac":
        return 86, 18, "SPACs often sound like a shortcut. Many never complete a quality deal."
    if sic in {"2834", "2836", "2833"}:
        return 74, 28, "Drug and biotech filings can look like lottery tickets. Read the science, the cash, and the risks."
    if sic == "6199" or any(word in name.lower() for word in ("crypto", "bitcoin", "etf")):
        return 81, 24, "Finance headlines move fast. A filing is not a business model."
    if sic in {"7372", "7371", "7370", "7374"}:
        return 66, 36, "Software stories are easy to love. Check whether customers actually pay."
    if form_type.endswith("/A"):
        return 40, 60, "An amendment means they are still revising the story. Slow down."
    if kind == "already_public":
        return 45, 55, "This may already trade. Extra shares can dilute, not mint overnight wealth."
    return 52, 48, "A registration is homework, not a jackpot."


def enrich_filing(row: dict[str, Any]) -> dict[str, Any]:
    filing = dict(row)
    filing["industry"] = industry_label(filing.get("sic"))
    filing["prospectus_url"], filing["index_url"] = document_urls(
        filing.get("cik") or "",
        filing.get("accession") or "",
        filing.get("primary_document") or "",
    )
    kind_info = classify_kind(filing.get("company") or "", filing.get("ticker"), filing.get("sic"))
    filing.update(kind_info)
    hype, reality, note = mock_hype_reality(
        filing.get("company") or "",
        filing.get("sic"),
        filing.get("form") or "",
        filing["kind"],
    )
    filing["hype"] = hype
    filing["reality"] = reality
    filing["note"] = note
    filing["filed_today"] = filing.get("filing_date") == date.today().isoformat()
    return filing


def snapshot_fields(filing: dict[str, Any]) -> dict[str, Any]:
    return {
        "company": filing["company"],
        "ticker": filing.get("ticker"),
        "cik": filing.get("cik") or "",
        "form": filing.get("form") or "",
        "filing_date": filing.get("filing_date") or "",
        "description": filing.get("description") or "",
        "sic": filing.get("sic"),
        "location": filing.get("location") or "—",
        "primary_document": filing.get("primary_document") or "",
        "accession": filing.get("accession") or "",
    }


class FilingFetchError(Exception):
    def __init__(self, message: str, kind: str = "error") -> None:
        super().__init__(message)
        self.kind = kind


def build_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent.strip(),
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json",
    }


@st.cache_data(ttl=300, show_spinner=False)
def fetch_s1_payload(user_agent: str, start: str, end: str, page_size: int) -> dict[str, Any]:
    params = {"forms": "S-1", "startdt": start, "enddt": end, "from": 0, "size": page_size}
    try:
        response = requests.get(
            SEARCH_URL,
            headers=build_headers(user_agent),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout as exc:
        raise FilingFetchError("The SEC took too long to answer. Showing saved filings instead.", kind="warning") from exc
    except requests.RequestException as exc:
        raise FilingFetchError("Could not reach the SEC right now. Showing saved filings instead.", kind="error") from exc

    if response.status_code == 403:
        raise FilingFetchError("The SEC blocked the live request. Check the Name + Email in Advanced settings.", kind="error")
    if response.status_code == 429:
        raise FilingFetchError("The SEC asked us to slow down. Showing saved filings for now.", kind="warning")
    if not response.ok:
        raise FilingFetchError(f"SEC returned HTTP {response.status_code}. Showing saved filings instead.", kind="error")

    try:
        payload = response.json()
    except ValueError as exc:
        raise FilingFetchError("The SEC response was not readable JSON.", kind="error") from exc
    if not isinstance(payload, dict):
        raise FilingFetchError("Unexpected SEC payload.", kind="error")
    return payload


def parse_filings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    hits = payload.get("hits", {}).get("hits", [])
    filings: list[dict[str, Any]] = []
    seen: set[str] = set()

    for hit in hits:
        source = hit.get("_source") or {}
        form_type = str(source.get("form") or source.get("file_type") or "").strip()
        root_forms = source.get("root_forms") or []
        if "S-1" not in root_forms and form_type not in {"S-1", "S-1/A"}:
            continue

        accession = str(source.get("adsh") or "")
        hit_id = str(hit.get("_id") or "")
        primary_document = hit_id.split(":", 1)[1] if ":" in hit_id else ""
        if not accession or not primary_document:
            continue

        key = f"{accession}:{primary_document}"
        if key in seen:
            continue
        seen.add(key)

        ciks = source.get("ciks") or []
        cik = str(ciks[0]).zfill(10) if ciks else ""
        names = source.get("display_names") or []
        company, ticker = parse_display_name(names[0] if names else "Unknown filer")
        sics = source.get("sics") or []
        locations = source.get("biz_locations") or []

        filings.append(
            enrich_filing(
                {
                    "company": company,
                    "ticker": ticker,
                    "cik": cik,
                    "form": form_type,
                    "filing_date": source.get("file_date") or "",
                    "description": source.get("file_description") or form_type,
                    "sic": str(sics[0]) if sics else None,
                    "location": locations[0] if locations else "—",
                    "primary_document": primary_document,
                    "accession": accession,
                }
            )
        )

    filings.sort(key=lambda row: (row["filing_date"], row["company"]), reverse=True)
    return filings


@st.cache_data(show_spinner=False)
def load_snapshot() -> list[dict[str, Any]]:
    if not SNAPSHOT_PATH.exists():
        return []
    try:
        raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw.get("filings", raw if isinstance(raw, list) else [])
    return [enrich_filing(row) for row in rows if isinstance(row, dict)]


def matches_query(filing: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        [
            filing.get("company") or "",
            filing.get("ticker") or "",
            filing.get("cik") or "",
            filing.get("industry") or "",
            filing.get("location") or "",
            filing.get("kind_label") or "",
            filing.get("form") or "",
        ]
    ).lower()
    return all(part in haystack for part in query.lower().split())


def format_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%b %d, %Y")
    except ValueError:
        return value or "—"


def meter_html(kind: str, value: int) -> str:
    css_track = "hype-track" if kind == "hype" else "reality-track"
    css_fill = "hype-fill" if kind == "hype" else "reality-fill"
    label = "Hype" if kind == "hype" else "Reality"
    return (
        f'<div class="meter-label"><span>{label}</span><span>{value}</span></div>'
        f'<div class="{css_track}"><div class="{css_fill}" style="width:{value}%"></div></div>'
    )


def chip_html(filing: dict[str, Any]) -> str:
    chips = []
    if filing.get("filed_today"):
        chips.append('<span class="filing-chip chip-today">Filed today</span>')
    if filing.get("form") == "S-1/A":
        chips.append('<span class="filing-chip chip-amend">Update to an older filing</span>')
    else:
        chips.append('<span class="filing-chip chip-s1">S-1 registration</span>')
    kind = filing.get("kind")
    if kind == "spac":
        chips.append(f'<span class="filing-chip chip-spac">{filing["kind_label"]}</span>')
    elif kind == "possible_ipo":
        chips.append(f'<span class="filing-chip chip-ipo">{filing["kind_label"]}</span>')
    else:
        chips.append(f'<span class="filing-chip chip-public">{filing["kind_label"]}</span>')
    chips.append(f'<span class="filing-chip chip-muted">{filing["industry"]}</span>')
    return " ".join(chips)


def render_card(filing: dict[str, Any], watchlist: set[str]) -> None:
    cik = filing.get("cik") or filing.get("accession")
    watched = cik in watchlist
    with st.container(border=True):
        st.markdown(chip_html(filing), unsafe_allow_html=True)
        title = filing["company"]
        if filing.get("ticker"):
            title = f"{title}  ·  {filing['ticker']}"
        st.subheader(title)

        meta = st.columns(3)
        meta[0].markdown(f"**Filed**  \n{format_date(filing['filing_date'])}")
        meta[1].markdown(f"**SEC ID (CIK)**  \n`{filing.get('cik') or '—'}`")
        meta[2].markdown(f"**Headquarters**  \n{filing.get('location') or '—'}")

        st.markdown(
            f'<div class="buy-box"><strong>Can uncle buy this in this app?</strong><br>{filing["buy_answer"]}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(meter_html("hype", filing["hype"]), unsafe_allow_html=True)
        st.markdown(meter_html("reality", filing["reality"]), unsafe_allow_html=True)
        st.caption(f"Hype vs. Reality is a teaching meter, not a rating. {filing['note']}")

        actions = st.columns([1.4, 1.4, 1])
        with actions[0]:
            st.link_button("Read the official prospectus", filing["prospectus_url"], use_container_width=True)
        with actions[1]:
            st.link_button("SEC filing index", filing["index_url"], use_container_width=True)
        with actions[2]:
            label = "Watching" if watched else "Watch"
            if st.button(label, key=f"watch_{filing['accession']}", use_container_width=True):
                if watched:
                    watchlist.discard(cik)
                else:
                    watchlist.add(cik)
                st.session_state.watchlist = sorted(watchlist)
                st.rerun()

        with st.expander("What to look for if you open the prospectus"):
            for item in CHECKLIST_ITEMS:
                st.markdown(f"**{item['title']}**  \n{item['prompt']}")


def render_table(filings: list[dict[str, Any]]) -> None:
    st.dataframe(
        [
            {
                "Company": row["company"],
                "Ticker": row.get("ticker") or "—",
                "What is it?": row["kind_label"],
                "Form": row["form"],
                "Filed": format_date(row["filing_date"]),
                "Industry": row["industry"],
                "Prospectus": row["prospectus_url"],
            }
            for row in filings
        ],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Prospectus": st.column_config.LinkColumn("Official prospectus", display_text="Open S-1"),
        },
    )


def load_desk(user_agent: str, start: date, end: date) -> tuple[list[dict[str, Any]], str, str | None]:
    snapshot = load_snapshot()
    source = "saved starter list"
    warning = None
    if not user_agent:
        return snapshot, source, None

    ua_ok, ua_message = looks_like_sec_user_agent(user_agent)
    if not ua_ok:
        return snapshot, source, ua_message

    try:
        payload = fetch_s1_payload(user_agent, start.isoformat(), end.isoformat(), 100)
        live = parse_filings(payload)
        if live:
            return live, "live SEC EDGAR", None
        warning = "The SEC search came back empty, so the saved starter list is still showing."
    except FilingFetchError as exc:
        warning = str(exc)
    return snapshot, source, warning


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
    inject_css()
    if "watchlist" not in st.session_state:
        st.session_state.watchlist = []
    watchlist = set(st.session_state.watchlist)

    saved_ua = secret_user_agent()
    user_agent = saved_ua
    lookback_days = 21
    view_mode = "Cards"
    with st.sidebar:
        st.markdown("### For Uncle")
        st.markdown(
            "Open the page. Filings should already be here. "
            "Search a name if you are curious. Read the prospectus if something looks exciting. "
            "There is still no magic Buy button."
        )
        st.divider()
        st.markdown("**The 30-second version**")
        st.markdown(
            "1. An **S-1** is paperwork: “we might offer stock.”\n"
            "2. Regular people usually **cannot** buy at a secret cheap IPO price.\n"
            "3. **SPACs** are often empty shells. We label those in pink."
        )
        with st.expander("How to read an S-1 without falling for hype"):
            for item in CHECKLIST_ITEMS:
                st.markdown(f"**{item['title']}**  \n{item['prompt']}")
        with st.expander("Advanced — SEC connection"):
            user_agent = st.text_input(
                "User-Agent (Name + Email)",
                value=saved_ua,
                help="Required by the SEC for live refreshes. On Streamlit Cloud, set this in Secrets so uncle never has to type it.",
            )
            lookback_days = st.slider("How far back to look", min_value=7, max_value=90, value=21, step=1)
            view_mode = st.radio("Layout", ["Cards", "Table"], horizontal=True)

        st.caption(f"Watching {len(watchlist)} compan{'y' if len(watchlist) == 1 else 'ies'} this session.")

    st.markdown('<div class="app-kicker">Research only · not a brokerage · SEC EDGAR</div>', unsafe_allow_html=True)
    st.title(APP_TITLE)
    st.markdown(
        '<p class="app-subtitle">The newest stock <em>paperwork</em>, already listed when you open the app. '
        "Search any company. Click through to the official SEC prospectus. "
        "This will not make anyone rich in five minutes — and that is the point.</p>",
        unsafe_allow_html=True,
    )
    st.info(
        "**You are looking at registration statements, not a hot-stock feed.** "
        "If a name looks exciting, that is the moment to slow down and read. "
        "Retail buyers typically face the public price later — including the famous IPO pop, or a drop."
    )

    query = st.text_input(
        "Search company, ticker, industry, or CIK",
        placeholder="Try Andersen, biotech, or SPAC",
    )
    filter_row = st.columns([2.2, 1.1, 1.1, 1])
    with filter_row[0]:
        kind_choice = st.selectbox("Show", list(KIND_FILTERS.keys()))
    with filter_row[1]:
        hide_amendments = st.toggle("Hide updates (S-1/A)", value=True)
    with filter_row[2]:
        hide_spacs = st.toggle("Hide SPAC shells", value=True)
    with filter_row[3]:
        recent_only = st.toggle("This week only", value=False)

    end = date.today()
    start = end - timedelta(days=lookback_days)

    with st.spinner("Putting the latest paperwork on the desk…"):
        filings, source, warning = load_desk(user_agent.strip(), start, end)

    if warning:
        st.warning(warning)
    if not filings:
        st.error("Nothing to show yet. Add a Name + Email under Advanced, or check the saved data file.")
        st.stop()

    week_cut = (end - timedelta(days=7)).isoformat()
    filtered = []
    for row in filings:
        if hide_amendments and row.get("form") == "S-1/A":
            continue
        if hide_spacs and row.get("kind") == "spac":
            continue
        if recent_only and (row.get("filing_date") or "") < week_cut:
            continue
        kind_wanted = KIND_FILTERS[kind_choice]
        if kind_wanted == "watchlist" and (row.get("cik") not in watchlist):
            continue
        if kind_wanted and kind_wanted != "watchlist" and row.get("kind") != kind_wanted:
            continue
        if not matches_query(row, query.strip()):
            continue
        filtered.append(row)

    possible = sum(1 for row in filings if row.get("kind") == "possible_ipo" and row.get("form") == "S-1")
    today_count = sum(1 for row in filings if row.get("filed_today"))
    spac_count = sum(1 for row in filings if row.get("kind") == "spac")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("On the desk", f"{len(filtered)} of {len(filings)}")
    m2.metric("Filed today", f"{today_count}")
    m3.metric("Possible new offerings", f"{possible}")
    m4.metric("SPAC shells in this pull", f"{spac_count}")
    st.caption(
        f"Source: {source} · {start.isoformat()} to {end.isoformat()} · "
        "live results refresh at most every 5 minutes · starter list ships with the app so the desk is never empty"
    )

    if not filtered:
        st.warning("Nothing matches those filters. Clear the search box or switch Show back to “Everything on the desk.”")
        st.stop()

    if view_mode == "Table":
        render_table(filtered)
    else:
        columns = st.columns(2)
        for index, filing in enumerate(filtered):
            with columns[index % 2]:
                render_card(filing, watchlist)

    st.markdown(
        '<p class="fine-print">Public SEC filings are not investment advice, IPO access, or a promise of profit. '
        "If this app ever feels like a shortcut to getting rich, close it and read the prospectus instead.</p>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
