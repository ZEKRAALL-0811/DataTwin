import streamlit as st
import pandas as pd
import logging
import plotly.graph_objects as go
from core.ai_engine import generate_code, generate_chat_explanation
from core.executor import execute_code

logger = logging.getLogger(__name__)

ACCENT = "#00f5d4"
TEXT_MUTED = "#a0a0a0"


def format_plotly_figure(fig):
    """Formats Plotly figures with a sleek, dark-themed appearance to match the DataTwin aesthetic."""
    if isinstance(fig, go.Figure):
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#1a1a1a",
            plot_bgcolor="#1a1a1a",
            font=dict(color="#ffffff", family="Outfit, Inter, sans-serif"),
            margin=dict(l=40, r=40, t=50, b=40),
            hoverlabel=dict(
                bgcolor="#2a2a2a",
                font_size=13,
                font_family="Outfit, Inter, sans-serif"
            )
        )
        # Apply clean dark gray lines for grid axes
        fig.update_xaxes(gridcolor="#2c2c2c", zerolinecolor="#3a3a3a")
        fig.update_yaxes(gridcolor="#2c2c2c", zerolinecolor="#3a3a3a")
        
        # Scrub pd.Interval objects from traces to prevent JSON serialization errors
        for trace in fig.data:
            for attr in ['x', 'y', 'z', 'customdata', 'text', 'hovertext']:
                val = getattr(trace, attr, None)
                if val is not None:
                    if isinstance(val, (pd.Series, pd.Index)):
                        if "interval" in str(val.dtype).lower() or isinstance(getattr(val, "dtype", None), pd.CategoricalDtype):
                            setattr(trace, attr, val.astype(str))
                    elif isinstance(val, list) and len(val) > 0 and type(val[0]).__name__ == 'Interval':
                        setattr(trace, attr, [str(v) if type(v).__name__ == 'Interval' else v for v in val])
                    elif str(type(val).__name__) == 'ndarray' and len(val) > 0 and type(val[0]).__name__ == 'Interval':
                        import numpy as np
                        setattr(trace, attr, np.array([str(v) if type(v).__name__ == 'Interval' else v for v in val]))
    return fig


def _render_explanation_box(explanation: str):
    """Render a styled 'What This Means' explanation box below charts/tables."""
    if not explanation or not explanation.strip():
        return

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #2a2a4a;
            border-left: 4px solid {ACCENT};
            border-radius: 10px;
            padding: 16px 20px;
            margin: 12px 0 8px 0;
        ">
            <div style="color: {ACCENT}; font-weight: 700; font-size: 0.95rem; margin-bottom: 10px;">
                💡 What This Means For You:
            </div>
            <div style="color: #d0d0d0; font-size: 0.88rem; line-height: 1.7;">
                {explanation}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _summarize_result(execution_result: dict) -> str:
    """Extract a text summary from execution results for the explanation LLM."""
    res_type = execution_result.get("type", "text")
    res_data = execution_result.get("data")

    if res_type == "text":
        return str(res_data)[:500] if res_data else ""
    elif res_type == "table":
        if isinstance(res_data, pd.DataFrame):
            return res_data.head(10).to_string()
        return str(res_data)[:500]
    elif res_type == "chart":
        # Extract chart data summary from the plotly figure
        if isinstance(res_data, go.Figure):
            summary_parts = []
            for trace in res_data.data:
                trace_name = getattr(trace, "name", "data")
                trace_type = trace.__class__.__name__
                summary_parts.append(f"Chart trace: {trace_name} (type: {trace_type})")
            layout = res_data.layout
            if layout.title and hasattr(layout.title, "text"):
                summary_parts.append(f"Chart title: {layout.title.text}")
            if layout.xaxis and layout.xaxis.title:
                x_title = layout.xaxis.title.text if hasattr(layout.xaxis.title, "text") else str(layout.xaxis.title)
                summary_parts.append(f"X-axis: {x_title}")
            if layout.yaxis and layout.yaxis.title:
                y_title = layout.yaxis.title.text if hasattr(layout.yaxis.title, "text") else str(layout.yaxis.title)
                summary_parts.append(f"Y-axis: {y_title}")
            return "\n".join(summary_parts)
        return "A plotly chart was generated."
    elif res_type == "error":
        return f"Error: {res_data}"
    return ""


def render_chat_page():
    """Renders the conversational interface for asking questions, displaying history, and executing code."""
    # Redirect if dataset is not loaded (safety fallback)
    if st.session_state.get("df") is None:
        st.session_state["current_page"] = "Upload"
        st.rerun()
        return

    df = st.session_state["df"]
    df_meta = st.session_state["df_meta"]

    st.markdown(
        """
        <div style="margin-bottom: 1.5rem;">
            <h2 style="color: #00f5d4; font-weight: 700; margin-bottom: 0.2rem;">💬 Query Your DataTwin</h2>
            <p style="color: #b0b0b0; font-size: 0.95rem;">Ask questions in plain English. Your DataTwin will analyze your data and explain the results in simple terms.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Generate dynamic suggestion chips based on column properties
    num_cols = df_meta.get("numeric_columns", [])
    cat_cols = df_meta.get("categorical_columns", [])
    date_cols = df_meta.get("datetime_columns", [])

    suggestions = []
    suggestions.append("Are there any missing values?")
    if num_cols:
        suggestions.append(f"What is the average of each numeric column?")
        suggestions.append(f"What are the top 5 rows by {num_cols[0]}?")
    if cat_cols:
        suggestions.append(f"Show frequency breakdown of {cat_cols[0]}")
    if len(num_cols) >= 2:
        suggestions.append("Show a correlation heatmap")
    elif date_cols:
        suggestions.append(f"Show me the trend over time by {date_cols[0]}")

    suggestions = suggestions[:5]  # Cap at 5 suggestion cards

    # Render suggestion chips if no chat history exists
    if not st.session_state["chat_history"]:
        st.markdown("<span style='color: #888888; font-size: 0.85rem; font-weight: 500; display:block; margin-bottom:10px;'>SUGGESTED QUESTIONS:</span>", unsafe_allow_html=True)
        cols = st.columns(len(suggestions))
        for idx, sug in enumerate(suggestions):
            with cols[idx]:
                if st.button(sug, key=f"sug_btn_{idx}", width='stretch'):
                    st.session_state["chat_history"].append({"role": "user", "content": sug})
                    st.rerun()

    # Display chat logs
    for msg_idx, msg in enumerate(st.session_state["chat_history"]):
        role = msg["role"]
        avatar = "🧬" if role == "ai" else None
        
        with st.chat_message(role, avatar=avatar):
            if role == "user":
                st.markdown(f"**{msg['content']}**")
            else:
                # Retrieve execution results
                content = msg.get("content")
                if content:
                    st.markdown(content)
                
                result_obj = msg.get("result", {})
                res_type = result_obj.get("type", "text")
                res_data = result_obj.get("data")

                if res_type == "text":
                    st.write(res_data)
                elif res_type == "chart":
                    formatted_chart = format_plotly_figure(res_data)
                    st.plotly_chart(formatted_chart, width='stretch')
                elif res_type == "table":
                    st.dataframe(res_data, width='stretch')
                elif res_type == "error":
                    st.error(res_data)

                # Show the "What This Means" explanation
                explanation = msg.get("explanation", "")
                if explanation:
                    _render_explanation_box(explanation)

                # Show code in expander
                code_snippet = msg.get("code")
                if code_snippet:
                    with st.expander("💻 View Generated Code"):
                        st.code(code_snippet, language="python")

                # Show suggested follow-ups
                followups = msg.get("suggested_followups", [])
                if followups:
                    st.markdown("<span style='color: #00f5d4; font-size: 0.85rem; font-weight: 600; display:block; margin-top:12px; margin-bottom:8px;'>🔍 Explore Further:</span>", unsafe_allow_html=True)
                    f_cols = st.columns(len(followups))
                    for idx, q in enumerate(followups):
                        with f_cols[idx]:
                            if st.button(q, key=f"followup_{msg_idx}_{idx}", width='stretch'):
                                st.session_state["chat_history"].append({"role": "user", "content": q})
                                st.rerun()

    # Handle query input
    user_query = st.chat_input("Ask anything about your dataset...")
    if user_query:
        st.session_state["chat_history"].append({"role": "user", "content": user_query})
        st.rerun()

    # Generate response loop if the last sender is user
    if st.session_state["chat_history"] and st.session_state["chat_history"][-1]["role"] == "user":
        last_query = st.session_state["chat_history"][-1]["content"]
        
        with st.status("🧠 DataTwin is analyzing your data...", expanded=True) as status:
            try:
                # Step 1: Generate code
                st.write("📝 Writing analysis code...")
                
                # Build conversation context from the last 3 ai messages
                history_list = [m for m in st.session_state["chat_history"] if m.get("role") == "ai" and "question" in m and "result_summary" in m]
                last_3 = history_list[-3:]
                context_str = ""
                if last_3:
                    context_str = "Previous questions and results:\n"
                    for i, m in enumerate(last_3, 1):
                        context_str += f"Q{i}: {m['question']} -> Result: {m['result_summary']}\n"
                    context_str += "\nNow answer the new question in that context."
                
                code = generate_code(last_query, df_meta, context_str)
                
                # Step 2: Execute code
                st.write("⚡ Running analysis on your dataset...")
                execution_result = execute_code(code, df)
                
                # Step 3: Generate plain-English explanation
                explanation = ""
                followups = []
                if execution_result["type"] != "error":
                    st.write("💡 Preparing easy-to-understand summary...")
                    result_summary = _summarize_result(execution_result)
                    explanation = generate_chat_explanation(last_query, result_summary, df_meta)
                    
                    st.write("🔍 Generating follow-up questions...")
                    from core.ai_engine import generate_followup_questions
                    followups = generate_followup_questions(last_query, result_summary)
                
                # Build the response
                if execution_result["type"] == "error":
                    ai_content = "I ran into an issue computing the results. Please check the details below or try rephrasing your request."
                else:
                    ai_content = "Here is the result of your analysis:"
                
                status.update(label="✅ Analysis complete!", state="complete", expanded=False)
                
                ai_message = {
                    "role": "ai",
                    "content": ai_content,
                    "code": code,
                    "result": execution_result,
                    "explanation": explanation,
                    "question": last_query,
                    "result_summary": result_summary if execution_result["type"] != "error" else execution_result["data"],
                    "suggested_followups": followups
                }
            except Exception as exc:
                logger.exception("AI query pipeline execution failed.")
                status.update(label="❌ Analysis failed", state="error", expanded=False)
                ai_message = {
                    "role": "ai",
                    "content": "AI is temporarily unavailable. Please try again.",
                    "code": "# Pipeline failed",
                    "result": {
                        "type": "error",
                        "data": "I couldn't answer that. Try rephrasing your question."
                    },
                    "explanation": "",
                }
            
            st.session_state["chat_history"].append(ai_message)
            st.rerun()
