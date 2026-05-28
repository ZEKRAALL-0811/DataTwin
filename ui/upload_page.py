import streamlit as st
import pandas as pd
import logging
from core.data_loader import load_file

logger = logging.getLogger(__name__)

def render_upload_page():
    """Renders the file upload UI, data preview, metadata statistics cards, and page navigation."""
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 style="color: #00f5d4; font-size: 3rem; font-weight: 800; margin-bottom: 0.5rem;">DataTwin</h1>
            <p style="color: #b0b0b0; font-size: 1.1rem;">Upload any CSV or Excel file to construct your dataset's digital twin</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Custom styling for streamlit file uploader to match dark theme
    st.markdown(
        """
        <style>
        .stFileUploader {
            background-color: #1a1a1a;
            border: 2px dashed #333333;
            border-radius: 12px;
            padding: 20px;
        }
        .stFileUploader:hover {
            border-color: #00f5d4;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    uploaded_file = st.file_uploader(
        "Upload CSV or Excel file",
        type=["csv", "xlsx", "xls"],
        label_visibility="collapsed"
    )

    if uploaded_file is not None:
        # Check if this is a new file or we already have it in session state
        if st.session_state.get("filename") != uploaded_file.name:
            with st.spinner("Reading, cleaning, and indexing your dataset..."):
                try:
                    df = load_file(uploaded_file)
                    st.session_state["filename"] = uploaded_file.name
                    # Clear session state items related to older dataset
                    st.session_state["chat_history"] = []
                    st.session_state["insights"] = None
                    logger.info("Successfully loaded file: %s", uploaded_file.name)
                except Exception as exc:
                    logger.exception("Failed to load file: %s", uploaded_file.name)
                    st.error("Unsupported file format or corrupt file. Please upload a valid CSV or Excel.")
                    return

        # If data is present in session state, render preview & metrics
        if "df" in st.session_state and "df_meta" in st.session_state:
            df = st.session_state["df"]
            meta = st.session_state["df_meta"]

            # Calculate and format file size
            file_bytes = len(uploaded_file.getvalue()) if hasattr(uploaded_file, "getvalue") else 0
            if file_bytes < 1024 * 1024:
                file_size_str = f"{file_bytes / 1024:.2f} KB"
            else:
                file_size_str = f"{file_bytes / (1024 * 1024):.2f} MB"

            st.write("---")
            st.markdown(f"### 📊 Dataset Overview: `{uploaded_file.name}`")

            # Metrics cards grid
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Rows", f"{meta['rows']:,}")
            with col2:
                st.metric("Columns", f"{meta['columns']:,}")
            with col3:
                total_missing = sum(meta["missing_values"].values())
                st.metric("Missing Values", f"{total_missing:,}")
            with col4:
                st.metric("File Size", file_size_str)

            # Inferred column type summary cards
            st.markdown("#### 🔍 Columns by Inferred Type")
            col_type_counts = {}
            for col, col_type in meta["column_types"].items():
                col_type_counts[col_type] = col_type_counts.get(col_type, 0) + 1

            type_columns = st.columns(max(len(col_type_counts), 1))
            for idx, (type_name, count) in enumerate(col_type_counts.items()):
                with type_columns[idx]:
                    st.markdown(
                        f"""
                        <div style="background-color: #1a1a1a; padding: 15px; border-radius: 10px; border-left: 4px solid #00f5d4; text-align: center; margin-bottom: 10px;">
                            <span style="color: #b0b0b0; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em;">{type_name}</span><br/>
                            <span style="color: #00f5d4; font-size: 1.6rem; font-weight: bold;">{count}</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            st.markdown(" ")

            # Detailed table of columns
            with st.expander("Show Column Details"):
                details_df = pd.DataFrame({
                    "DataType": [meta["dtypes"][col] for col in meta["column_names"]],
                    "Inferred Class": [meta["column_types"][col] for col in meta["column_names"]],
                    "Missing Count": [meta["missing_values"][col] for col in meta["column_names"]],
                    "Missing Percentage": [f"{meta['missing_percentages'][col]}%" for col in meta["column_names"]]
                }, index=meta["column_names"])
                st.dataframe(details_df, width='stretch')

            # Data Preview Section
            st.markdown("#### 📄 Dataset Preview (First 10 rows)")
            st.dataframe(df.head(10), width='stretch')

            # Proceed Button
            st.markdown("<br/>", unsafe_allow_html=True)
            if st.button("🚀 Analyze This Data", width='stretch'):
                st.session_state["current_page"] = "Insights"
                st.rerun()
    else:
        # If no file uploaded, prompt the user to load one
        st.info("Please drag and drop or upload a dataset file above to start.")
