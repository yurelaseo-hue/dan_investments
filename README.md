# Uncle's IPO & Stock Prospectus Finder

A **read-only** research desk for your uncle: recent SEC Form S-1 filings, already listed when the page opens, with search and plain-English labels.

- GitHub: [yurelaseo-hue/dan_investments](https://github.com/yurelaseo-hue/dan_investments)
- One-click deploy: [Streamlit Community Cloud](https://share.streamlit.io/deploy?repository=yurelaseo-hue/dan_investments&branch=main&mainModule=app.py)

This is not a brokerage, not IPO allocation, and not a way to get rich from a “magic app.” An S-1 is paperwork that says a company *might* offer stock.

## What uncle sees

- A starter list of real recent S-1 filings the moment the app loads
- A live refresh from SEC EDGAR when a Name + Email User-Agent is configured
- Search by company, ticker, CIK, industry, or words like `biotech` / `SPAC`
- Filters for possible new offerings, companies that may already trade, and blank-check SPACs
- A Watch list for this session
- A direct link to the official prospectus on sec.gov
- A “Can uncle buy this in this app?” answer on every card: **no**

## Run locally

```powershell
python -m pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Edit `.streamlit/secrets.toml` and put a real name plus your email (the SEC requires it):

```toml
[sec]
user_agent = "Dan Investments Research you@email.com"
```

Then:

```powershell
python -m streamlit run app.py
```

The app will still open and show the bundled starter list even if live EDGAR is unavailable.

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (already the intended workflow).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **Create app**.
4. Choose this repository, branch `main`, and main file `app.py`.
5. Under **Advanced settings → Secrets**, paste:

```toml
[sec]
user_agent = "Dan Investments Research you@email.com"
```

6. Deploy. After that, opening the cloud URL should show filings immediately — uncle does not type a User-Agent.

Community Cloud rebuilds the app when you push to GitHub.

## Project layout

- `app.py` — the dashboard
- `data/latest_filings.json` — starter list so the desk is never empty
- `requirements.txt` — Python packages
- `.streamlit/config.toml` — dark theme
- `.streamlit/secrets.toml.example` — copy for local secrets (do not commit the real file)

## Honest limits

- Retail investors usually cannot buy at a special insider IPO price.
- Many S-1s are from companies that **already trade**, or from **SPAC shells**, not classic IPOs.
- Hype vs. Reality meters are teaching tools, not ratings or advice.
