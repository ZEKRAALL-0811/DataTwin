import streamlit as st
import os
from dotenv import load_dotenv

# Load environmental configurations
load_dotenv()

# Streamlit page layout and header details
st.set_page_config(
    page_title="DataTwin - Living Digital Twin of Your Data",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Force premium dark mode look with custom CSS rules
st.markdown(
    """
    <style>
    /* Main application background colors */
    [data-testid="stAppViewContainer"] {
        background-color: #0e0e0e;
        color: #ffffff;
    }
    [data-testid="stHeader"] {
        background-color: rgba(14, 14, 14, 0.8) !important;
        backdrop-filter: blur(8px);
    }
    
    /* Navigation Sidebar customizations */
    [data-testid="stSidebar"] {
        background-color: #161616 !important;
        border-right: 1px solid #222222;
    }
    
    /* Typography customizations */
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff;
        font-family: 'Outfit', 'Inter', sans-serif;
    }
    
    /* Theme color variables custom inputs styling */
    .stTextInput>div>div>input {
        background-color: #1a1a1a;
        color: #ffffff;
        border: 1px solid #333333;
        border-radius: 8px;
    }
    .stTextInput>div>div>input:focus {
        border-color: #00f5d4;
    }
    
    /* Metrics panel customizations */
    div[data-testid="metric-container"] {
        background-color: #1a1a1a;
        border: 1px solid #2a2a2a;
        border-radius: 10px;
        padding: 12px 18px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    div[data-testid="metric-container"] label {
        color: #a0a0a0 !important;
        font-size: 0.85rem !important;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #00f5d4 !important;
        font-size: 1.8rem !important;
        font-weight: 700;
    }
    
    /* Custom buttons style adjustments */
    div.stButton > button {
        background-color: #1a1a1a;
        color: #ffffff;
        border: 1px solid #333333;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        transition: all 0.3s ease;
    }
    div.stButton > button:hover {
        border-color: #00f5d4;
        color: #00f5d4;
        background-color: #1a1a1a;
        box-shadow: 0 0 10px rgba(0, 245, 212, 0.2);
    }
    div.stButton > button:active {
        background-color: #00f5d4;
        color: #0e0e0e;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Pre-initialize required Session State variables
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Upload"
if "df" not in st.session_state:
    st.session_state["df"] = None
if "df_meta" not in st.session_state:
    st.session_state["df_meta"] = None
if "filename" not in st.session_state:
    st.session_state["filename"] = None
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# Sidebar Navigation Control Center
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 15px 0px; text-align: center;">
            <h2 style="color: #00f5d4; font-weight: 800; letter-spacing: 0.05em; margin-bottom: 0px;">🧬 DataTwin</h2>
            <p style="color: #777777; font-size: 0.85rem; margin-top: 4px;">Dataset Digital Twin Interface</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("---")

    # If dataset has been uploaded, display short summary and provide navigation controls
    if st.session_state["df"] is not None:
        _sidebar_display_name = "🔗 Live Google Sheet" if st.session_state.get("data_source") == "google_sheet" else st.session_state.get("filename", "Dataset")
        st.markdown(
            f"""
            <div style="background-color: #1a1a1a; padding: 12px; border-radius: 8px; border-left: 3px solid #00f5d4; margin-bottom: 20px;">
                <span style="color: #888888; font-size: 0.75rem; text-transform: uppercase; font-weight: 600;">ACTIVE DATASET</span><br/>
                <span style="font-weight: 700; font-size: 0.95rem; color: #ffffff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; margin-top: 3px;">{_sidebar_display_name}</span>
                <span style="color: #a0a0a0; font-size: 0.8rem; display: block; margin-top: 2px;">{st.session_state['df_meta']['rows']:,} rows &bull; {st.session_state['df_meta']['columns']:,} cols</span>
            </div>
            """,
            unsafe_allow_html=True
        )

        pages = ["Upload", "Insights", "Chat", "Forecast"]
        
        # Sync the widget key with current_page BEFORE creating the widget to avoid StreamlitAPIException
        if "navigation_sidebar_menu" in st.session_state and st.session_state["navigation_sidebar_menu"] != st.session_state["current_page"]:
            del st.session_state["navigation_sidebar_menu"]

        # Sync the radio index from current_page (allows buttons on other pages to navigate)
        current_idx = pages.index(st.session_state["current_page"]) if st.session_state["current_page"] in pages else 0

        selected_page = st.radio(
            "Navigation Menu",
            options=pages,
            index=current_idx,
            key="navigation_sidebar_menu",
            label_visibility="collapsed",
            on_change=lambda: st.session_state.update({"current_page": st.session_state["navigation_sidebar_menu"]}),
        )

        st.markdown("---")
        
        # Reset / Upload New dataset option
        if st.button("📤 Upload New Dataset", width='stretch'):
            st.session_state["df"] = None
            st.session_state["df_meta"] = None
            st.session_state["filename"] = None
            st.session_state["chat_history"] = []
            st.session_state["insights"] = None
            st.session_state["current_page"] = "Upload"
            st.rerun()
            
        # Data Privacy: Clear all session state
        st.markdown("<br/>", unsafe_allow_html=True)
        if st.button("🗑️ Clear Session & Data", width='stretch', type='primary'):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    else:
        st.markdown(
            """
            <div style="background-color: #1a1a1a; padding: 15px; border-radius: 8px; border: 1px dashed #333333; text-align: center; margin-bottom: 20px;">
                <span style="color: #666666; font-size: 0.85rem; font-weight: 500;">No active dataset uploaded</span>
            </div>
            """,
            unsafe_allow_html=True
        )
        # Force redirection to upload if missing
        st.session_state["current_page"] = "Upload"

# Route application page output
current_view = st.session_state["current_page"]

if current_view == "Upload":
    from ui.upload_page import render_upload_page
    render_upload_page()
elif current_view == "Insights":
    try:
        from ui.insights_page import render_insights_page
        render_insights_page()
    except ImportError:
        st.markdown("### 🔍 Insights (Coming Soon)")
        st.info("Insights dashboard features are currently being built. Head over to the **Chat** tab to query your data in plain English!")
elif current_view == "Chat":
    from ui.chat_page import render_chat_page
    render_chat_page()
elif current_view == "Forecast":
    try:
        from ui.forecast_page import render_forecast_page
        render_forecast_page()
    except ImportError:
        st.markdown("### 🔮 Forecasting (Coming Soon)")
        st.info("Predictive forecasting features are currently being built. Head over to the **Chat** tab to query your data in plain English!")
