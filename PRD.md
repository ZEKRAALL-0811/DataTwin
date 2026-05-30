# DataTwin — Product Requirements Document (PRD)

## 1. Product Overview

**DataTwin** is a Streamlit-based AI-powered data analysis platform. Users upload CSV/Excel files or connect a Google Sheet, and the app creates a "digital twin" of their dataset — generating automated insights, a chat interface for asking questions in plain English, and time-series forecasting.

**URL**: `http://localhost:8501`
**Framework**: Streamlit (Python)
**No login required** — the app is open access.

---

## 2. Pages & Navigation

The app has 4 pages, navigated via a sidebar radio menu:

| Page | URL Path | Description |
|------|----------|-------------|
| **Upload** | `/` (default) | File upload, Google Sheet connector, data preview, health score, auto-cleaning |
| **Insights** | `/` (same URL, different state) | Auto-generated charts and AI explanations |
| **Chat** | `/` (same URL, different state) | Natural language Q&A with data |
| **Forecast** | `/` (same URL, different state) | Time-series forecasting with Prophet |

> Note: Streamlit is a single-page app. All pages share the same URL (`/`). Navigation is handled via sidebar radio buttons that change `st.session_state["current_page"]`.

---

## 3. Feature Specifications

### 3.1 Upload Page (Default Landing Page)

**Elements visible on load:**
- Page title: "DataTwin" in large cyan text
- Subtitle: "Upload a file or connect a Google Sheet..."
- File uploader accepting `.csv`, `.xlsx`, `.xls`
- Privacy notice banner (green info box)
- Divider "── or ──"
- Google Sheet URL text input field
- "🔗 Connect Sheet" button
- Placeholder text: "👆 Choose one of the options above to get started"

**After uploading a file:**
- Dataset Overview section with 4 metric cards: Rows, Columns, Missing Values, Data Size
- "Columns by Inferred Type" cards (numeric, categorical, datetime)
- "Show Column Details" expandable section
- "Dataset Preview (First 10 rows)" table with sensitive columns masked as "••••••••"
- **Data Health Score** — Plotly circular gauge (0-100) with 3 progress bars (Completeness, Consistency, Format Readiness)
- **Automated Data Cleaning Agent** — Either "Data Issues Found" card (red) with "✨ Auto-Clean My Data" button, OR "Data Looks Clean!" card (green)
- After cleaning: "Cleaning Report" card (green) with checkmarks + "📥 Download Cleaned Dataset" button
- "🚀 Analyze This Data" button to navigate to Insights

**After connecting Google Sheet:**
- Same behavior as file upload, but sidebar shows "🔗 Live Google Sheet"

### 3.2 Insights Page

**Elements visible:**
- Auto-generated charts (distribution plots, correlation heatmaps, bar charts)
- Plain-English explanation below each chart
- "Generate Data Story" button → executive summary card with download
- Navigation buttons: "Ask Questions in Chat" and "Forecast Trends"

### 3.3 Chat Page

**Elements visible:**
- Chat input field at bottom
- User types a question → AI generates Python code → code executes safely → result displayed
- Results can be: charts (Plotly), tables (DataFrames), or text
- "What This Means For You" section with 3-5 bullet points below each result
- Chat history persisted during session

### 3.4 Forecast Page

**Elements visible:**
- Dropdowns to select date column and value column
- Forecast chart with confidence intervals
- Navigation buttons: "Back to Insights" and "Ask Questions in Chat"

---

## 4. Sidebar

**When no dataset is loaded:**
- "🧬 DataTwin" branding
- "No active dataset uploaded" placeholder

**When dataset is loaded:**
- "🧬 DataTwin" branding
- Active dataset card showing filename/source, row count, column count
- Navigation radio: Upload, Insights, Chat, Forecast
- "📤 Upload New Dataset" button
- "🗑️ Clear Session & Data" button

---

## 5. Data Privacy Features

1. Privacy notice banner on upload page
2. Sensitive columns (email, phone, password, ssn, id, address, dob) are auto-masked with "••••••••" and 🔒 icon
3. "Clear Session & Data" button wipes all session state

---

## 6. Key User Flows

### Flow 1: Upload → Preview → Clean → Analyze
1. User opens app at localhost:8501
2. User uploads a CSV file
3. Data preview appears with metrics, column types, and preview table
4. Health Score gauge shows current data quality
5. If issues found, user clicks "✨ Auto-Clean My Data"
6. Cleaning report appears, health score updates
7. User clicks "🚀 Analyze This Data" → navigates to Insights

### Flow 2: Google Sheet → Analyze
1. User pastes a Google Sheet URL
2. User clicks "🔗 Connect Sheet"
3. Same preview/clean/analyze flow as above

### Flow 3: Chat with Data
1. User navigates to Chat page via sidebar
2. User types a question like "Show me the top 5 products by revenue"
3. AI generates code, executes it, displays chart/table
4. Plain English explanation appears below the result

### Flow 4: Generate Forecast
1. User navigates to Forecast page
2. User selects a date column and a value column
3. Prophet generates a forecast with confidence intervals
