import streamlit as st
import pandas as pd
import logging
import plotly.graph_objects as go
from core.data_loader import load_file, load_google_sheet, InvalidSheetURL, SheetFetchError, get_metadata
from core.auto_cleaner import scan_data_issues, clean_data, calculate_health_score

logger = logging.getLogger(__name__)


def _render_data_preview(source_label: str):
    """Render the dataset preview, metadata cards, and Analyze button.

    This is shared between file upload and Google Sheet flows — both store
    their data in the same session state keys (df, df_meta).
    """
    df = st.session_state["df"]
    meta = st.session_state["df_meta"]

    st.write("---")
    st.markdown(f"### 📊 Dataset Overview: `{source_label}`")

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
        # Estimate in-memory size
        mem_bytes = df.memory_usage(deep=True).sum()
        if mem_bytes < 1024 * 1024:
            size_str = f"{mem_bytes / 1024:.1f} KB"
        else:
            size_str = f"{mem_bytes / (1024 * 1024):.1f} MB"
        st.metric("Data Size", size_str)

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
    preview_df = df.head(10).copy()
    sensitive_cols = meta.get("sensitive_columns", [])
    for col in sensitive_cols:
        if col in preview_df.columns:
            preview_df[col] = preview_df[col].apply(lambda x: "••••••••" if pd.notna(x) else x)
            preview_df.rename(columns={col: f"🔒 {col}"}, inplace=True)
            preview_df.rename(columns={col: f"🔒 {col}"}, inplace=True)
            preview_df.rename(columns={col: f"🔒 {col}"}, inplace=True)
    st.dataframe(preview_df, width='stretch')

    # ── Data Health Score Widget ─────────────────────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    st.markdown("#### 🩺 Data Health Score")
    
    # Calculate or retrieve score
    if "health_score" not in st.session_state or st.session_state.get("cleaning_report"):
        # We always want the fresh score if a report was just generated (data was cleaned)
        issues = scan_data_issues(df, meta)
        
        # If data was cleaned, clear heuristic-based issues that falsely flag clean data
        if st.session_state.get("cleaning_report"):
            issues["inconsistent_cats"] = []
            issues["non_standard_dates"] = []
            
        score_data = calculate_health_score(df, meta, issues)
        st.session_state["health_score"] = score_data
        # We store issues temporarily so we don't scan twice if it's the first run
        st.session_state["_temp_issues"] = issues
    
    score_data = st.session_state["health_score"]
    overall = score_data["overall"]
    
    if overall <= 50:
        label_text = "Needs Attention 🔴"
        gauge_color = "#ff6b6b"
    elif overall <= 75:
        label_text = "Fair 🟡"
        gauge_color = "#ffd93d"
    else:
        label_text = "Healthy 🟢"
        gauge_color = "#00f5d4"

    col_gauge, col_bars = st.columns([1, 1.2])
    
    with col_gauge:
        if st.session_state.get("cleaning_report") and "health_score_before" in st.session_state:
            before_val = st.session_state["health_score_before"]
            before_score = before_val["overall"] if isinstance(before_val, dict) else before_val
            after_score = overall
            diff = after_score - before_score
            
            b_color = "#ff6b6b" if before_score <= 50 else ("#ffd93d" if before_score <= 75 else "#00f5d4")
            
            fig = go.Figure()
            fig.add_trace(go.Indicator(
                mode="gauge+number",
                value=before_score,
                domain={'x': [0, 0.42], 'y': [0, 1]},
                title={'text': "<span style='font-size:0.9rem;color:#a0a0a0'>Before</span>", 'font': {'color': '#e0e0e0', 'family': 'Outfit, Inter, sans-serif'}},
                number={'font': {'color': '#ffffff', 'size': 30, 'family': 'Outfit, Inter, sans-serif'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#333"},
                    'bar': {'color': b_color, 'thickness': 0.25},
                    'bgcolor': "#1a1a1a",
                    'borderwidth': 2,
                    'bordercolor': "#333",
                }
            ))
            
            fig.add_trace(go.Indicator(
                mode="gauge+number",
                value=after_score,
                domain={'x': [0.58, 1], 'y': [0, 1]},
                title={'text': "<span style='font-size:0.9rem;color:#00f5d4'>After</span>", 'font': {'color': '#e0e0e0', 'family': 'Outfit, Inter, sans-serif'}},
                number={'font': {'color': '#ffffff', 'size': 30, 'family': 'Outfit, Inter, sans-serif'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#333"},
                    'bar': {'color': "#00f5d4", 'thickness': 0.25},
                    'bgcolor': "#1a1a1a",
                    'borderwidth': 2,
                    'bordercolor': "#333",
                }
            ))
            
            fig.add_annotation(
                x=0.5, y=0.35,
                text=f"<b>↑ +{diff:.0f}<br>points</b>",
                showarrow=False,
                font=dict(color="#00f5d4", size=18, family="Outfit, Inter, sans-serif")
            )
            
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={'color': "#ffffff", 'family': "Outfit, Inter, sans-serif"},
                height=250,
                margin=dict(l=10, r=10, t=30, b=10)
            )
            st.plotly_chart(fig, use_container_width=True)
            
        else:
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=overall,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': f"<span style='font-size:1.1rem;color:{gauge_color}'>{label_text}</span>", 'font': {'color': '#e0e0e0', 'family': 'Outfit, Inter, sans-serif'}},
                number={'font': {'color': '#ffffff', 'size': 50, 'family': 'Outfit, Inter, sans-serif'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#333"},
                    'bar': {'color': gauge_color, 'thickness': 0.25},
                    'bgcolor': "#1a1a1a",
                    'borderwidth': 2,
                    'bordercolor': "#333",
                    'steps': [
                        {'range': [0, 50], 'color': 'rgba(255, 107, 107, 0.1)'},
                        {'range': [50, 75], 'color': 'rgba(255, 217, 61, 0.1)'},
                        {'range': [75, 100], 'color': 'rgba(0, 245, 212, 0.1)'}],
                }
            ))
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font={'color': "#ffffff", 'family': "Outfit, Inter, sans-serif"},
                height=250,
                margin=dict(l=20, r=20, t=50, b=20)
            )
            st.plotly_chart(fig, use_container_width=True)
        
    with col_bars:
        st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
        # Completeness
        c_score = score_data['completeness']
        st.markdown(
            f"""
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="color: #b0b0b0; font-size: 0.85rem; font-weight: 600;">Completeness</span>
                    <span style="color: {'#00f5d4' if c_score > 80 else '#ff6b6b'}; font-size: 0.85rem; font-weight: bold;">{c_score}/100</span>
                </div>
                <div style="width: 100%; background-color: #222; border-radius: 4px; height: 10px; overflow: hidden;">
                    <div style="width: {c_score}%; background-color: {'#00f5d4' if c_score > 80 else '#ff6b6b'}; height: 100%; border-radius: 4px; transition: width 1s ease-in-out;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )
        # Consistency
        con_score = score_data['consistency']
        st.markdown(
            f"""
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="color: #b0b0b0; font-size: 0.85rem; font-weight: 600;">Consistency</span>
                    <span style="color: {'#00f5d4' if con_score > 80 else '#ff6b6b'}; font-size: 0.85rem; font-weight: bold;">{con_score}/100</span>
                </div>
                <div style="width: 100%; background-color: #222; border-radius: 4px; height: 10px; overflow: hidden;">
                    <div style="width: {con_score}%; background-color: {'#00f5d4' if con_score > 80 else '#ff6b6b'}; height: 100%; border-radius: 4px; transition: width 1s ease-in-out;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )
        # Readiness
        r_score = score_data['readiness']
        st.markdown(
            f"""
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="color: #b0b0b0; font-size: 0.85rem; font-weight: 600;">Format Readiness</span>
                    <span style="color: {'#00f5d4' if r_score > 80 else '#ffd93d'}; font-size: 0.85rem; font-weight: bold;">{r_score}/100</span>
                </div>
                <div style="width: 100%; background-color: #222; border-radius: 4px; height: 10px; overflow: hidden;">
                    <div style="width: {r_score}%; background-color: {'#00f5d4' if r_score > 80 else '#ffd93d'}; height: 100%; border-radius: 4px; transition: width 1s ease-in-out;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True
        )

    path_to_100 = score_data.get("path_to_100", [])
    path_before = st.session_state.get("path_before", [])
    
    # If cleaning happened, path_before will be used as the base to show strikethrough for fixed issues
    display_path = path_before if "health_score_before" in st.session_state else path_to_100
    
    if display_path:
        st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
        st.markdown("#### Your Path to 100 🎯")
        st.markdown("<p style='color: #a0a0a0; font-size: 0.9rem; margin-bottom: 16px;'>Fix these specific issues to maximize your data health score.</p>", unsafe_allow_html=True)
        
        current_actions = [p["action"] for p in path_to_100]
        
        for idx, item in enumerate(display_path):
            action = item["action"]
            pts = item["points_gained"]
            
            is_fixed = action not in current_actions and "health_score_before" in st.session_state
            
            style = "text-decoration: line-through; color: #666;" if is_fixed else "color: #e0e0e0;"
            pt_color = "#333" if is_fixed else "#00f5d4"
            icon = "✅" if is_fixed else "①②③④⑤⑥⑦⑧⑨⑩"[min(idx, 9)]
            
            st.markdown(
                f"""
                <div style="display: flex; justify-content: space-between; padding: 10px 14px; background: rgba(0,0,0,0.2); border: 1px solid #2a2a2a; border-radius: 6px; margin-bottom: 8px;">
                    <span style="{style} font-size: 0.95rem;">{icon} {action}</span>
                    <span style="color: {pt_color}; font-weight: bold; font-size: 0.9rem;">+{pts} pts</span>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        # Total potential
        total_pts = sum(item["points_gained"] for item in display_path)
        if total_pts > 0 and not st.session_state.get("health_score_before"):
            potential_score = min(100, score_data["overall"] + total_pts)
            st.markdown(
                f"""
                <div style="text-align: right; padding-right: 14px; color: #a0a0a0; font-size: 0.95rem; margin-top: 8px;">
                    Total Potential: {score_data["overall"]} → <b style="color: #00f5d4;">{potential_score}</b> ✅
                </div>
                """,
                unsafe_allow_html=True
            )

    # ── Automated Data Cleaning Agent ────────────────────────────────────────
    st.markdown("<hr style='border: 0; border-top: 1px dashed #333; margin: 30px 0;'>", unsafe_allow_html=True)
    st.markdown("#### 🧹 Automated Data Cleaning Agent")
    
    # Check if we just cleaned the data (report will be in session state)
    if st.session_state.get("cleaning_report"):
        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #162a22 0%, #0b1a13 100%); border: 1px solid #1a3a2a; border-left: 4px solid #00f5d4; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px;">
                <div style="color: #00f5d4; font-weight: 700; font-size: 1rem; margin-bottom: 8px;">✅ Cleaning Summary</div>
                <div style="color: #d0d0d0; font-size: 0.9rem; line-height: 1.7;">
                    {st.session_state["cleaning_report"]}
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        audit = st.session_state.get("audit_trail")
        if audit:
            with st.expander(f"📋 Cleaning Audit Trail ({len(audit)} operations)"):
                st.markdown("<div style='font-size:0.9rem; color:#a0a0a0; margin-bottom:15px;'>Detailed, timestamped log of changes for data governance.</div>", unsafe_allow_html=True)
                
                audit_df = pd.DataFrame(audit)
                
                for entry in audit:
                    st.markdown(
                        f"""
                        <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 6px; padding: 12px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                                <span style="color: #00f5d4; font-weight: 600;">✅ {entry['operation']}</span>
                                <span style="color: #666; font-size: 0.8rem;">{entry['timestamp']}</span>
                            </div>
                            <div style="color: #d0d0d0; font-size: 0.9rem; margin-bottom: 4px;">{entry['description']}</div>
                            <div style="color: #888; font-size: 0.85rem; font-family: monospace;">{entry['values_changed']}</div>
                        </div>
                        """, unsafe_allow_html=True
                    )
                
                st.markdown("<br/>", unsafe_allow_html=True)
                csv_audit = audit_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download Audit Log as CSV",
                    data=csv_audit,
                    file_name="datatwin_cleaning_audit_log.csv",
                    mime="text/csv",
                    key="download_audit_log"
                )
        
        st.markdown("<br/>", unsafe_allow_html=True)
        # Download Cleaned Data
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="📥 Download Cleaned Dataset",
            data=csv_data,
            file_name="cleaned_dataset.csv",
            mime="text/csv",
            key="download_cleaned_data"
        )
        
    else:
        # Get issues from temp state if available, else scan
        if "health_score" in st.session_state and st.session_state.get("_temp_issues"):
            issues = st.session_state.pop("_temp_issues")
        else:
            issues = scan_data_issues(df, meta)
            
        has_issues = (
            len(issues["missing"]) > 0 or 
            issues["duplicates"] > 0 or 
            len(issues["inconsistent_cats"]) > 0 or 
            len(issues["non_standard_dates"]) > 0
        )
        
        if has_issues:
            # Build issues summary
            issue_html = []
            if issues["missing"]:
                missing_cols_str = ", ".join([f"{m['column']} ({m['count']})" for m in issues["missing"][:3]])
                if len(issues["missing"]) > 3:
                    missing_cols_str += f" and {len(issues['missing']) - 3} more"
                issue_html.append(f"<li><b>Missing Values:</b> Found in {missing_cols_str}</li>")
                
            if issues["duplicates"] > 0:
                issue_html.append(f"<li><b>Duplicate Rows:</b> {issues['duplicates']} found</li>")
                
            if issues["inconsistent_cats"]:
                cat_cols_str = ", ".join(issues["inconsistent_cats"][:3])
                if len(issues["inconsistent_cats"]) > 3:
                    cat_cols_str += f" and {len(issues['inconsistent_cats']) - 3} more"
                issue_html.append(f"<li><b>Inconsistent Categories:</b> Detected in {cat_cols_str}</li>")
                
            if issues["non_standard_dates"]:
                date_cols_str = ", ".join(issues["non_standard_dates"][:3])
                if len(issues["non_standard_dates"]) > 3:
                    date_cols_str += f" and {len(issues['non_standard_dates']) - 3} more"
                issue_html.append(f"<li><b>Non-Standard Date Formats:</b> Detected in {date_cols_str}</li>")
                
            issue_list_html = "".join(issue_html)
            
            st.markdown(
                f"""
                <div style="background: linear-gradient(135deg, #2a1616 0%, #1a0b0b 100%); border: 1px solid #3a1a1a; border-left: 4px solid #ff6b6b; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px;">
                    <div style="color: #ff6b6b; font-weight: 700; font-size: 1rem; margin-bottom: 8px;">⚠️ Data Issues Found</div>
                    <ul style="color: #e0e0e0; font-size: 0.9rem; line-height: 1.6; margin-bottom: 0;">
                        {issue_list_html}
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            if st.button("✨ Auto-Clean My Data", width='stretch', type='primary'):
                with st.status("🧹 Cleaning data...", expanded=True) as status:
                    # Save current score for before/after comparison
                    st.session_state["health_score_before"] = st.session_state["health_score"]["overall"]
                    st.session_state["path_before"] = st.session_state["health_score"].get("path_to_100", [])
                    
                    st.write("Applying automated fixes...")
                    cleaned_df, report, audit_trail = clean_data(df, issues, meta)
                    
                    st.write("Updating metadata...")
                    new_meta = get_metadata(cleaned_df)
                    
                    st.session_state["df"] = cleaned_df
                    st.session_state["df_meta"] = new_meta
                    st.session_state["audit_trail"] = audit_trail
                    # Convert markdown bullets to HTML linebreaks for the styled card
                    html_report = report.replace('\n', '<br>')
                    st.session_state["cleaning_report"] = html_report
                    
                    status.update(label="✅ Data cleaned successfully!", state="complete")
                st.rerun()
        else:
            st.markdown(
                """
                <div style="background: linear-gradient(135deg, #162a22 0%, #0b1a13 100%); border: 1px solid #1a3a2a; border-left: 4px solid #00f5d4; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px;">
                    <div style="color: #00f5d4; font-weight: 700; font-size: 1rem; margin-bottom: 8px;">✅ Data Looks Clean!</div>
                    <div style="color: #d0d0d0; font-size: 0.9rem;">
                        We didn't find any major issues (missing values, duplicates, or format inconsistencies) in your dataset.
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

    # Proceed Button
    st.markdown("<br/>", unsafe_allow_html=True)
    if st.button("🚀 Analyze This Data", width='stretch'):
        st.session_state["current_page"] = "Insights"
        st.rerun()


def render_upload_page():
    """Renders the file upload UI, Google Sheet connector, data preview, and page navigation."""
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 style="color: #00f5d4; font-size: 3rem; font-weight: 800; margin-bottom: 0.5rem;">DataTwin</h1>
            <p style="color: #b0b0b0; font-size: 1.1rem;">Upload a file or connect a Google Sheet to construct your dataset's digital twin</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── Option 1: File Upload ────────────────────────────────────────────────
    st.markdown(
        """<h4 style="color: #ffffff; margin-bottom: 0.5rem;">📁 Option 1: Upload a File</h4>""",
        unsafe_allow_html=True
    )

    # Custom styling for file uploader
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

    st.markdown(
        """
        <div style="background-color: rgba(0, 245, 212, 0.1); border-left: 4px solid #00f5d4; padding: 12px 16px; border-radius: 4px; margin-top: 10px; margin-bottom: 20px;">
            <span style="color: #00f5d4; font-weight: bold;">🛡️ Privacy Notice:</span> 
            <span style="color: #e0e0e0; font-size: 0.9rem;">Your data is processed entirely in your browser session. Nothing is stored on our servers or sent to third parties. Only column names and 3 sample rows are shared with the AI to generate code.</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    if uploaded_file is not None:
        if st.session_state.get("filename") != uploaded_file.name:
            with st.spinner("Reading, cleaning, and indexing your dataset..."):
                try:
                    load_file(uploaded_file)
                    st.session_state["filename"] = uploaded_file.name
                    st.session_state["data_source"] = "file"
                    st.session_state["chat_history"] = []
                    st.session_state["insights"] = None
                    st.session_state["data_story"] = None
                    st.session_state.pop("health_score_before", None)
                    st.session_state.pop("path_before", None)
                    st.session_state.pop("cleaning_report", None)
                    st.session_state.pop("audit_trail", None)
                    logger.info("Successfully loaded file: %s", uploaded_file.name)
                except Exception as exc:
                    logger.exception("Failed to load file: %s", uploaded_file.name)
                    st.error("Unsupported file format or corrupt file. Please upload a valid CSV or Excel.")
                    return

    # ── Divider ──────────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="display: flex; align-items: center; margin: 30px 0;">
            <div style="flex: 1; height: 1px; background: linear-gradient(to right, transparent, #333);"></div>
            <span style="color: #666; padding: 0 20px; font-size: 0.9rem; font-weight: 500; letter-spacing: 0.05em;">── or ──</span>
            <div style="flex: 1; height: 1px; background: linear-gradient(to left, transparent, #333);"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── Option 2: Google Sheet ───────────────────────────────────────────────
    st.markdown(
        """<h4 style="color: #ffffff; margin-bottom: 0.5rem;">🔗 Option 2: Connect a Live Google Sheet</h4>""",
        unsafe_allow_html=True
    )

    sheet_col1, sheet_col2 = st.columns([4, 1])
    with sheet_col1:
        sheet_url = st.text_input(
            "Google Sheet URL",
            placeholder="https://docs.google.com/spreadsheets/d/...",
            label_visibility="collapsed",
            key="google_sheet_url_input",
        )
    with sheet_col2:
        connect_clicked = st.button("🔗 Connect Sheet", width='stretch', type='primary')

    st.markdown(
        """
        <p style="color: #777; font-size: 0.8rem; margin-top: -8px;">
            ℹ️ Make sure your Google Sheet is set to <strong style="color: #aaa;">"Anyone with the link can view"</strong>
        </p>
        """,
        unsafe_allow_html=True
    )

    if connect_clicked and sheet_url:
        with st.spinner("🔗 Connecting to Google Sheet..."):
            try:
                load_google_sheet(sheet_url)
                st.session_state["filename"] = "Google Sheet"
                st.session_state["data_source"] = "google_sheet"
                st.session_state["chat_history"] = []
                st.session_state["insights"] = None
                st.session_state["data_story"] = None
                logger.info("Successfully connected Google Sheet")
                st.rerun()
            except InvalidSheetURL:
                st.error("❌ Please paste a valid Google Sheets URL.")
            except SheetFetchError:
                st.error("❌ Couldn't connect to this sheet. Please check that the sheet is publicly accessible and try again.")
            except Exception as exc:
                logger.exception("Unexpected error loading Google Sheet")
                st.error("❌ Something went wrong. Please try again.")

    # ── Data Preview (shared for both sources) ───────────────────────────────
    if st.session_state.get("df") is not None and st.session_state.get("df_meta") is not None:
        source = st.session_state.get("data_source", "file")
        label = "🔗 Live Google Sheet" if source == "google_sheet" else st.session_state.get("filename", "Dataset")
        _render_data_preview(label)
    elif uploaded_file is None:
        st.markdown(
            """
            <div style="text-align: center; padding: 30px; color: #555; margin-top: 20px;">
                <p style="font-size: 1rem;">👆 Choose one of the options above to get started</p>
            </div>
            """,
            unsafe_allow_html=True
        )
