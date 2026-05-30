# DataTwin — Complete Knowledge Transfer Document

> **Purpose**: Paste this entire document into the first message of your new Antigravity IDE session so the AI has full context of everything built so far. Do not skip any section.

---

## 1. Project Identity

| Field | Value |
|-------|-------|
| **Project Name** | DataTwin |
| **Description** | A Streamlit-based AI-powered data analysis platform that creates a "digital twin" of any uploaded dataset. Users can upload CSV/Excel files or connect Google Sheets, get auto-generated insights, chat with their data in plain English, and run time-series forecasts. |
| **Repo** | `ZEKRAALL-0811/DataTwin` on GitHub |
| **Local Path** | `d:\Outskill(DataTwin)` |
| **Language** | Python 3.11 |
| **Framework** | Streamlit (>=1.35.0) |
| **LLM Provider** | **Groq** (was originally Gemini, migrated due to free-tier rate limits) |
| **LLM Model** | `llama-3.3-70b-versatile` |
| **Deployment Target** | Render.com (free tier) |
| **Start Command** | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |

---

## 2. Target Audience — CRITICAL RULE

> **DataTwin's users are NON-TECHNICAL** — business owners, students, and professionals who have never heard terms like "correlation heatmap", "distribution", or "outliers".

### Mandatory Rules for ALL AI-Generated Content:
- Every chart explanation must use **plain English** — ZERO jargon
- Never use words like: "Pearson", "coefficient", "variance", "statistically significant", "regression", "standard deviation", "skew"
- Instead say: "strongly connected", "tends to go up together", "no clear pattern"
- Every chat response must include both the chart/table AND a "What This Means" section with 3-5 non-technical bullet points
- Every insight bullet must answer "So what does this mean for me?" from a business perspective

---

## 3. API Keys & Secrets

> [!CAUTION]
> These are live API keys. The `.env` and `.streamlit/secrets.toml` files are gitignored.

| Key | Value | Location |
|-----|-------|----------|
| **Groq API Key** | `your_groq_api_key_here` | `.env` as `GROQ_API_KEY` and `.streamlit/secrets.toml` |
| **TestSprite MCP API Key** | `your_testsprite_api_key_here` | IDE MCP config (`mcp_config.json`) |

### `.env` file contents:
```
GROQ_API_KEY=your_groq_api_key_here
```

### `.streamlit/secrets.toml` contents:
```toml
GROQ_API_KEY = "your_groq_api_key_here"
```

### `.env.example` (committed to git — no real key):
```
GROQ_API_KEY=your_groq_api_key_here
```
> [!NOTE]
> The `.env.example` still says GEMINI_API_KEY. This should be updated to `GROQ_API_KEY=your_groq_api_key_here` in a future commit.

---

## 4. Complete File Tree & Purpose

```
d:\Outskill(DataTwin)\
├── .env                          # Real Groq API key (gitignored)
├── .env.example                  # Placeholder for contributors (needs updating)
├── .gitignore                    # Ignores .env, secrets.toml, __pycache__, .gemini/, .agent/, .gsd/
├── .streamlit/
│   ├── config.toml               # Streamlit server config (headless, no CORS, no XSRF, no usage stats)
│   └── secrets.toml              # Groq API key for Streamlit secrets (gitignored)
├── app.py                        # Main entry point — page routing, sidebar, session state init, CSS
├── requirements.txt              # All pip dependencies
├── runtime.txt                   # python-3.11.0 (for Render deployment)
├── core/
│   ├── __init__.py               # Empty init
│   ├── auto_cleaner.py           # Data issue scanning, health score calculation, auto-cleaning logic
│   ├── codex_engine.py           # LLM integration — code gen, explanations, data story, category standardization
│   ├── data_loader.py            # File loading, Google Sheets fetching, DataFrame cleaning, metadata extraction
│   └── executor.py               # Sandboxed code execution with AST safety checks and timeout
├── ui/
│   ├── upload_page.py            # File upload + Google Sheets + data preview + health score + auto-cleaner UI
│   ├── insights_page.py          # Auto-generated charts, insights, data story, navigation buttons
│   ├── chat_page.py              # Natural language Q&A with code gen + execution + explanation
│   └── forecast_page.py          # Time-series forecasting with Prophet
├── PRD.md                        # Product requirements document
├── PROJECT_RULES.md              # Development rules and conventions
├── brainstorming.txt             # Early brainstorming notes
└── progress.txt                  # Progress tracking notes
```

---

## 5. Architecture Deep Dive

### 5.1 Data Pipeline Flow

```
User uploads CSV/Excel/Google Sheet
        │
        ▼
core/data_loader.py
  ├── load_file() or load_google_sheet()
  ├── clean_dataframe()  →  normalize cols, trim strings, parse dates
  └── get_metadata()     →  returns dict with rows, columns, dtypes, column_types,
                             missing_values, missing_percentages, numeric_columns,
                             categorical_columns, datetime_columns, sensitive_columns, sample
        │
        ▼
st.session_state["df"]      ← cleaned DataFrame
st.session_state["df_meta"] ← metadata dict
st.session_state["filename"] ← e.g. "sales_data.csv"
st.session_state["data_source"] ← "file" or "google_sheet"
```

### 5.2 LLM Pipeline (core/codex_engine.py)

```
User question → build_system_prompt(df_meta) → call_llm(system, user)
                                                       │
                                                       ▼
                                               Groq API (llama-3.3-70b-versatile)
                                                       │
                                                       ▼
                                         _strip_markdown_code_fence()
                                                       │
                                                       ▼
                                              Raw Python code string
```

**Key functions in codex_engine.py:**
| Function | Purpose |
|----------|---------|
| `build_system_prompt(df_meta)` | Builds the system prompt with dataset schema for code generation |
| `generate_code(question, df_meta)` | Generates Python code to answer a user question |
| `generate_explanation(context, df_meta)` | Generates plain-English chart/insight explanations |
| `generate_chat_explanation(question, result_summary, df_meta)` | Generates "What This Means" section for chat |
| `generate_data_story(insights_text, df_meta)` | Generates ~200-word executive summary narrative |
| `standardize_categories(column_name, unique_values)` | Asks LLM to map messy categorical values to standardized form |
| `call_llm(system_prompt, user_question)` | Core Groq API call with `temperature=0` |
| `call_gemini(...)` / `call_openai(...)` | Backward-compatible aliases that route to `call_llm` |
| `_get_api_key()` | Reads `GROQ_API_KEY` from env |

### 5.3 Code Execution Sandbox (core/executor.py)

- Uses `ast.parse()` to statically analyze generated code before running it
- Blocks dangerous imports: `os`, `sys`, `subprocess`, `shutil`, `socket`, etc.
- Blocks dangerous functions: `open`, `exec`, `eval`, `compile`, `__import__`
- Blocks dangerous attributes: `__globals__`, `__code__`, `__subclasses__`
- Allows only: `pandas`, `numpy`, `plotly`, `scipy`, `sklearn`, and safe stdlib modules
- Runs code in a daemon thread with a **30-second timeout**
- Pre-injects `pd`, `np`, `px`, `go`, `df` into the execution namespace
- Result must be stored in a variable called `result`

### 5.4 Auto-Cleaning Pipeline (core/auto_cleaner.py)

| Function | Purpose |
|----------|---------|
| `scan_data_issues(df, meta)` | Detects missing values, duplicates, inconsistent categories, non-standard dates |
| `calculate_health_score(df, meta, issues)` | Computes Completeness, Consistency, Readiness sub-scores + Overall 0-100 |
| `clean_data(df, issues, meta)` | Cleans a COPY of the df: dedup → fill missing (median/mode) → LLM category standardization → date parsing |

**Health Score Formula:**
- **Completeness** = 100 - (% missing cells)
- **Consistency** = 100 - (duplicate% × 10) - (inconsistent_cats_count × 15)
- **Readiness** = (typed_columns / total_columns) × 100
- **Overall** = average of the three

**Score Labels:**
- 0-50: "Needs Attention 🔴" (red gauge)
- 51-75: "Fair 🟡" (yellow gauge)
- 76-100: "Healthy 🟢" (cyan gauge)

---

## 6. Session State Keys

| Key | Type | Purpose |
|-----|------|---------|
| `current_page` | str | Active page: "Upload", "Insights", "Chat", "Forecast" |
| `df` | DataFrame | The active dataset |
| `df_meta` | dict | Metadata from `get_metadata()` |
| `filename` | str | Original filename or "Google Sheet" |
| `data_source` | str | "file" or "google_sheet" |
| `chat_history` | list | Chat messages list |
| `insights` | varies | Cached insights data |
| `data_story` | str | Generated executive summary |
| `health_score` | dict | `{overall, completeness, consistency, readiness}` |
| `cleaning_report` | str | HTML string of the cleaning report |
| `_temp_issues` | dict | Temporary storage of scanned issues (popped after use) |

---

## 7. UI Pages Detail

### 7.1 Upload Page (`ui/upload_page.py`)
- **Header**: "DataTwin" title with subtitle
- **Option 1**: File uploader (CSV/Excel) with privacy notice banner
- **Divider**: "── or ──"
- **Option 2**: Google Sheet URL input + "🔗 Connect Sheet" button
- **Data Preview**: Dataset overview metrics (rows, cols, missing, size), column type cards, column details expander, first 10 rows with sensitive column masking (🔒)
- **Health Score Widget**: Plotly gauge chart + 3 HTML progress bars
- **Auto-Cleaning Agent**: Issues card → "✨ Auto-Clean My Data" button → Cleaning Report card → "📥 Download Cleaned Dataset" button
- **Navigate**: "🚀 Analyze This Data" button

### 7.2 Insights Page (`ui/insights_page.py`)
- Auto-generated charts: distribution plots, correlation heatmaps, top-N bar charts
- Plain-English explanations below each chart (generated by LLM)
- "Generate Data Story" button → executive summary card with download button
- Navigation buttons to Chat and Forecast pages

### 7.3 Chat Page (`ui/chat_page.py`)
- Natural language Q&A interface
- User types question → LLM generates Python code → executor runs it safely → result displayed
- Every response includes both the chart/table AND a "What This Means For You" section
- Chat history persisted in session state

### 7.4 Forecast Page (`ui/forecast_page.py`)
- Time-series forecasting using Facebook Prophet
- User selects date column and value column
- Generates forecast chart with confidence intervals
- Navigation buttons back to Insights and Chat

---

## 8. Design System & Styling

| Element | Value |
|---------|-------|
| **Background** | `#0e0e0e` (near-black) |
| **Sidebar** | `#161616` |
| **Card Background** | `#1a1a1a` |
| **Primary Accent** | `#00f5d4` (Cyan/Mint) |
| **Error/Warning** | `#ff6b6b` (Coral Red) |
| **Fair/Moderate** | `#ffd93d` (Gold) |
| **Text Primary** | `#ffffff` |
| **Text Secondary** | `#b0b0b0` / `#a0a0a0` |
| **Text Muted** | `#666666` / `#555` |
| **Borders** | `#333333` / `#2a2a2a` |
| **Font Family** | `'Outfit', 'Inter', sans-serif` |
| **Button Hover** | Cyan border glow `box-shadow: 0 0 10px rgba(0, 245, 212, 0.2)` |

All custom CSS is injected in `app.py` via `st.markdown()` with `unsafe_allow_html=True`.

---

## 9. Data Privacy Features

1. **Privacy Notice Banner**: Green info box below file uploader stating data stays in browser session
2. **Sensitive Column Auto-Masking**: Detects columns with keywords (`email`, `phone`, `password`, `ssn`, `id`, `address`, `dob`) and masks preview values with `••••••••` + 🔒 icon
3. **Session Cleanup**: Sidebar "🗑️ Clear Session & Data" button that wipes all `st.session_state` keys
4. **Sample Data Masking**: The 3-row sample sent to the LLM also has sensitive columns masked

---

## 10. Google Sheets Integration

- Uses the **public CSV export URL** pattern: `https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv`
- No OAuth, no API keys, no external dependencies (uses Python's built-in `urllib`)
- Sheet must be set to "Anyone with the link can view"
- Sheet ID extracted from URL via regex: `/spreadsheets/d/([a-zA-Z0-9-_]+)/`
- Custom exceptions: `InvalidSheetURL` and `SheetFetchError`

---

## 11. Known Issues & Gotchas

| Issue | Details |
|-------|---------|
| **Plotly datetime vlines** | `add_vline` doesn't work with datetime objects. Use `add_shape` + `add_annotation` instead. |
| **`infer_datetime_format` deprecated** | Already fixed — removed from `auto_cleaner.py`. Use `pd.to_datetime(..., errors='coerce')` without it. |
| **Duplicate rename calls** | In `upload_page.py` lines 79-81, `preview_df.rename` for sensitive columns is called 3 times (a harmless bug from accumulated edits). Should be deduplicated. |
| **`.env.example` outdated** | Still references `GEMINI_API_KEY`. Should be updated to `GROQ_API_KEY`. |
| **Groq rate limits** | Groq free tier allows 30 requests/minute (much better than Gemini's 5/minute). If the user is on a paid plan, this is not an issue. |
| **Prophet installation** | Prophet can be tricky to install on some systems. It's in `requirements.txt` but may fail on Render's free tier. |

---

## 12. Configuration Files

### `.streamlit/config.toml`
```toml
[server]
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
```

### `runtime.txt`
```
python-3.11.0
```

### `requirements.txt`
```
streamlit>=1.35.0
pandas>=2.2.0
numpy>=1.26.0
plotly>=5.22.0
groq>=0.9.0
python-dotenv>=1.0.1
openpyxl>=3.1.2
xlrd>=2.0.1
scipy>=1.13.0
scikit-learn>=1.5.0
prophet>=1.1.5
```

---

## 13. Sidebar Navigation Logic

- Uses `st.radio` with `on_change` callback to sync `st.session_state["current_page"]`
- Other pages can set `current_page` directly and call `st.rerun()` to navigate
- When no dataset is loaded, sidebar forces `current_page = "Upload"`
- "Upload New Dataset" button resets `df`, `df_meta`, `filename`, `chat_history`, `insights`
- "Clear Session & Data" button deletes ALL session state keys

---

## 14. Render Deployment Config

| Field | Value |
|-------|-------|
| **Name** | datatwin |
| **Branch** | main |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` |
| **Environment Variable** | `GROQ_API_KEY` = (the Groq key above) |

---

## 15. TestSprite MCP Configuration

The user was in the process of setting up TestSprite for automated webpage testing. The MCP config file is at `c:\Users\skzah\.gemini\config\mcp_config.json`:

```json
{
  "mcpServers": {
    "TestSprite": {
      "command": "npx",
      "args": [
        "-y",
        "@testsprite/testsprite-mcp@latest"
      ],
      "env": {
        "API_KEY": "sk-user-eT4DLKsecN-CAkkhbseIov7qXZ0HynufZlcyrOi21j0lIiL6Ev8KmhD0Kh6T1HLES2vk-YGsRUI4EtqX98DeN_y8X7ASIF4IRghmA5-mSoLLzHfWI8ulwKpsBMERaAh9oq0"
      }
    }
  }
}
```

---

## 16. Features NOT Yet Built (Future Roadmap)

| Feature | Status | Notes |
|---------|--------|-------|
| **Hero/Landing Page** | NOT STARTED | Beautiful "About" page explaining what DataTwin is |
| **Download/Export Module** | NOT STARTED | Export buttons for generated charts, tables, and forecast data |
| **TestSprite Integration** | IN PROGRESS | MCP config was added to IDE but not yet tested |
| **Commit Pending Changes** | NOT DONE | All the features below have NOT been committed to git yet |

---

## 17. Complete History of Changes (Since Last Git Commit)

### Change 1: Data Story Generator
- Added `generate_data_story()` in `core/codex_engine.py`
- Added "Generate Data Story" button + executive summary card + download button in `ui/insights_page.py`

### Change 2: Google Sheets Integration
- Added `InvalidSheetURL`, `SheetFetchError` exceptions + `load_google_sheet()` in `core/data_loader.py`
- Updated `ui/upload_page.py` with split UI: File Upload vs. Google Sheet
- Updated `app.py` sidebar to show "🔗 Live Google Sheet" for sheet data sources

### Change 3: Automated Data Cleaning Agent
- Created `core/auto_cleaner.py` (NEW file) with `scan_data_issues()`, `clean_data()`
- Added `standardize_categories()` in `core/codex_engine.py` for LLM-powered category mapping
- Updated `ui/upload_page.py` with "Data Issues Found" card, "✨ Auto-Clean My Data" button, Cleaning Report card, "📥 Download Cleaned Dataset" button

### Change 4: Data Health Score Widget
- Added `calculate_health_score()` in `core/auto_cleaner.py`
- Updated `ui/upload_page.py` with Plotly circular gauge + 3 HTML progress bars
- Score recalculates and animates after cleaning

### Change 5: Migration from Gemini to Groq
- Replaced `google-genai` with `groq` in `requirements.txt`
- Updated `.env` from `GEMINI_API_KEY` to `GROQ_API_KEY`
- Created `.streamlit/secrets.toml` with Groq key
- Completely rewrote `call_llm()` in `core/codex_engine.py` to use Groq Python client
- Changed `DEFAULT_MODEL` from `gemini-2.5-flash` to `llama-3.3-70b-versatile`
- Added backward-compatible `call_gemini()` and `call_openai()` aliases

---

## 18. Important Conventions

1. **temperature=0** for all LLM calls (deterministic outputs)
2. **Never modify original DataFrame** during cleaning — always work on a copy
3. **All cleaning steps wrapped in try/except** — if one fails, skip it silently
4. **Downstream pages are source-agnostic** — they only read `st.session_state["df"]` and `st.session_state["df_meta"]`, never caring if data came from file or Google Sheet
5. **No `statsmodels`** — it's not installed. Use scikit-learn for regression.
6. **Use `urllib` instead of `requests`** for Google Sheets — avoids extra dependency on Render free tier
7. **Sensitive columns** are auto-detected by keyword and masked in both the preview table AND the sample data sent to the LLM
