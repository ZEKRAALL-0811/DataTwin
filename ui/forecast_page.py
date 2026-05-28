import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging

logger = logging.getLogger(__name__)

# ── Design Tokens ────────────────────────────────────────────────────────────
ACCENT = "#00f5d4"
ACCENT_2 = "#7b61ff"
BG_PLOT = "#1a1a1a"
TEXT_MUTED = "#a0a0a0"
TEXT_WHITE = "#ffffff"
GRID_COLOR = "#2c2c2c"

PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=BG_PLOT,
    plot_bgcolor=BG_PLOT,
    font=dict(color=TEXT_WHITE, family="Outfit, Inter, sans-serif", size=12),
    margin=dict(l=40, r=40, t=50, b=40),
    hoverlabel=dict(bgcolor="#2a2a2a", font_size=13, font_family="Outfit, Inter, sans-serif"),
)


def _section_header(title: str, subtitle: str = ""):
    html = f"""
    <div style="margin-top: 2rem; margin-bottom: 1rem;">
        <h3 style="color: {ACCENT}; font-weight: 700; margin-bottom: 0.2rem;">{title}</h3>
        {"<p style='color: " + TEXT_MUTED + "; font-size: 0.9rem; margin-top: 0;'>" + subtitle + "</p>" if subtitle else ""}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _explanation_box(explanation: str):
    """Render a styled explanation box below a chart."""
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
            margin: 8px 0 20px 0;
        ">
            <div style="color: {ACCENT}; font-weight: 700; font-size: 0.9rem; margin-bottom: 8px;">
                💡 What This Means For You:
            </div>
            <div style="color: #d0d0d0; font-size: 0.85rem; line-height: 1.7;">
                {explanation}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric_card(label: str, value: str, color: str = ACCENT):
    return f"""
    <div style="
        background: linear-gradient(135deg, #1a1a1a 0%, #222222 100%);
        border: 1px solid #2a2a2a;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    ">
        <div style="color: {color}; font-size: 1.5rem; font-weight: 700;">{value}</div>
        <div style="color: {TEXT_MUTED}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 4px;">{label}</div>
    </div>
    """


def _prepare_prophet_df(df: pd.DataFrame, date_col: str, target_col: str) -> pd.DataFrame:
    """Prepare a DataFrame for Prophet: columns must be 'ds' and 'y'."""
    prophet_df = df[[date_col, target_col]].copy()
    prophet_df.columns = ["ds", "y"]
    prophet_df["ds"] = pd.to_datetime(prophet_df["ds"], errors="coerce")
    prophet_df = prophet_df.dropna(subset=["ds", "y"])

    # Aggregate duplicates by date (sum or mean depending on context)
    prophet_df = prophet_df.groupby("ds", as_index=False)["y"].sum()
    prophet_df = prophet_df.sort_values("ds").reset_index(drop=True)

    return prophet_df


def _run_prophet_forecast(prophet_df: pd.DataFrame, periods: int, freq: str):
    """Run Prophet and return (model, forecast DataFrame)."""
    from prophet import Prophet

    # Suppress Prophet's verbose logging
    import logging as _logging
    _logging.getLogger("prophet").setLevel(_logging.WARNING)
    _logging.getLogger("cmdstanpy").setLevel(_logging.WARNING)

    model = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        changepoint_prior_scale=0.05,
    )
    model.fit(prophet_df)

    future = model.make_future_dataframe(periods=periods, freq=freq)
    forecast = model.predict(future)

    return model, forecast


def _detect_frequency(prophet_df: pd.DataFrame) -> str:
    """Detect the most likely frequency of the time series."""
    if len(prophet_df) < 3:
        return "D"

    diffs = prophet_df["ds"].diff().dropna()
    median_days = diffs.dt.days.median()

    if median_days <= 1:
        return "D"
    elif median_days <= 7:
        return "W"
    elif median_days <= 31:
        return "MS"
    elif median_days <= 92:
        return "QS"
    else:
        return "YS"


FREQ_LABELS = {
    "D": "Daily",
    "W": "Weekly",
    "MS": "Monthly",
    "QS": "Quarterly",
    "YS": "Yearly",
}


# ═════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ═════════════════════════════════════════════════════════════════════════════
def render_forecast_page():
    """Render the forecasting page with Prophet-based predictions."""
    if st.session_state.get("df") is None:
        st.session_state["current_page"] = "Upload"
        st.rerun()
        return

    df: pd.DataFrame = st.session_state["df"]
    meta: dict = st.session_state["df_meta"]

    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem;">
            <h2 style="color: {ACCENT}; font-weight: 700; margin-bottom: 0.2rem;">🔮 Predict Future Trends</h2>
            <p style="color: {TEXT_MUTED}; font-size: 0.95rem;">
                Your DataTwin looks at your past data to predict what might happen next.
                It finds repeating patterns (like weekly or yearly cycles) and uses them to estimate future values.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    date_cols = meta.get("datetime_columns", [])
    num_cols = meta.get("numeric_columns", [])

    # ── Guard: need at least 1 date + 1 numeric column ────────────────────
    if not date_cols:
        st.warning("⚠️ No date/time columns detected in your dataset. Forecasting requires at least one date column.")
        st.info("💡 Go back to the **Chat** tab and ask questions about your data instead.")
        return

    if not num_cols:
        st.warning("⚠️ No numeric columns detected. Forecasting requires at least one numeric column to predict.")
        return

    # ── Configuration Panel ───────────────────────────────────────────────
    _section_header("⚙️ Configure Forecast")

    col1, col2, col3 = st.columns(3)

    with col1:
        date_col = st.selectbox(
            "📅 Date Column",
            options=date_cols,
            index=0,
            key="forecast_date_col",
        )

    with col2:
        target_col = st.selectbox(
            "🎯 Target Column (predict this)",
            options=num_cols,
            index=0,
            key="forecast_target_col",
        )

    # Prepare data to detect frequency
    prophet_df = _prepare_prophet_df(df, date_col, target_col)
    detected_freq = _detect_frequency(prophet_df)

    with col3:
        periods = st.slider(
            "🔢 Forecast Periods",
            min_value=7,
            max_value=365,
            value=90,
            step=7,
            key="forecast_periods",
            help=f"Number of future {FREQ_LABELS.get(detected_freq, 'time units').lower()} periods to predict",
        )

    # Show data quality summary
    st.markdown(
        f"""
        <div style="background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 10px; padding: 14px 20px; margin: 10px 0 20px 0;">
            <span style="color: {TEXT_MUTED}; font-size: 0.85rem;">
                📊 <strong style="color:{TEXT_WHITE}">{len(prophet_df):,}</strong> data points &nbsp;•&nbsp;
                📅 <strong style="color:{TEXT_WHITE}">{prophet_df['ds'].min().strftime('%b %Y')}</strong> → <strong style="color:{TEXT_WHITE}">{prophet_df['ds'].max().strftime('%b %Y')}</strong> &nbsp;•&nbsp;
                ⏱️ Detected frequency: <strong style="color:{ACCENT}">{FREQ_LABELS.get(detected_freq, detected_freq)}</strong>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if len(prophet_df) < 10:
        st.error("❌ Not enough data points for forecasting. Need at least 10 rows with valid dates and values.")
        return

    # ── Run Forecast ──────────────────────────────────────────────────────
    run_btn = st.button("🚀 Generate Forecast", width='stretch', key="run_forecast_btn")

    if run_btn or st.session_state.get("_forecast_result") is not None:
        if run_btn:
            with st.spinner("🔮 Prophet is analyzing patterns and generating forecast..."):
                try:
                    model, forecast = _run_prophet_forecast(prophet_df, periods, detected_freq)
                    st.session_state["_forecast_result"] = {
                        "model": model,
                        "forecast": forecast,
                        "prophet_df": prophet_df,
                        "target_col": target_col,
                        "date_col": date_col,
                        "periods": periods,
                        "freq": detected_freq,
                    }
                except Exception as exc:
                    logger.exception("Prophet forecasting failed.")
                    st.error(f"❌ Forecasting failed: {exc}")
                    return

        result = st.session_state["_forecast_result"]
        forecast = result["forecast"]
        prophet_df = result["prophet_df"]
        target_col_name = result["target_col"]

        # ── Forecast Metrics Cards ────────────────────────────────────────
        _section_header("📊 Forecast Summary")

        historical_mean = prophet_df["y"].mean()
        forecast_future = forecast[forecast["ds"] > prophet_df["ds"].max()]
        forecast_mean = forecast_future["yhat"].mean() if len(forecast_future) > 0 else 0
        trend_change = ((forecast_mean - historical_mean) / historical_mean * 100) if historical_mean != 0 else 0
        trend_dir = "📈 Upward" if trend_change > 1 else ("📉 Downward" if trend_change < -1 else "➡️ Stable")
        trend_color = "#6bcb77" if trend_change > 1 else ("#ff6b6b" if trend_change < -1 else ACCENT)

        cols = st.columns(5)
        metrics = [
            ("Historical Mean", f"{historical_mean:,.1f}", ACCENT),
            ("Forecast Mean", f"{forecast_mean:,.1f}", ACCENT_2),
            ("Trend Direction", trend_dir, trend_color),
            ("Change %", f"{trend_change:+.1f}%", trend_color),
            ("Forecast Points", str(len(forecast_future)), TEXT_MUTED),
        ]
        for col, (label, value, color) in zip(cols, metrics):
            with col:
                st.markdown(_metric_card(label, value, color), unsafe_allow_html=True)

        st.markdown("<br/>", unsafe_allow_html=True)

        # ── 1. Main Forecast Chart ────────────────────────────────────────
        _section_header("🔮 Forecast vs Actual", f"Predicted {target_col_name} with 95% confidence interval")

        fig = go.Figure()

        # Historical data
        fig.add_trace(go.Scatter(
            x=prophet_df["ds"],
            y=prophet_df["y"],
            mode="markers",
            name="Actual Data",
            marker=dict(color=ACCENT, size=4, opacity=0.6),
        ))

        # Forecast line
        fig.add_trace(go.Scatter(
            x=forecast["ds"],
            y=forecast["yhat"],
            mode="lines",
            name="Forecast",
            line=dict(color=ACCENT_2, width=2),
        ))

        # Confidence interval
        fig.add_trace(go.Scatter(
            x=pd.concat([forecast["ds"], forecast["ds"][::-1]]),
            y=pd.concat([forecast["yhat_upper"], forecast["yhat_lower"][::-1]]),
            fill="toself",
            fillcolor="rgba(123, 97, 255, 0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name="95% Confidence",
            hoverinfo="skip",
        ))

        # Vertical line at forecast start
        if len(forecast_future) > 0:
            forecast_start = forecast_future["ds"].iloc[0]
            fig.add_shape(
                type="line",
                x0=forecast_start, x1=forecast_start,
                y0=0, y1=1,
                yref="paper",
                line=dict(color="#ffd93d", width=1.5, dash="dash"),
                opacity=0.6,
            )
            fig.add_annotation(
                x=forecast_start, y=1.05, yref="paper",
                text="Forecast Start",
                showarrow=False,
                font=dict(color="#ffd93d", size=11),
            )

        fig.update_layout(
            **PLOT_LAYOUT,
            height=500,
            xaxis_title="Date",
            yaxis_title=target_col_name,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=11),
            ),
        )
        fig.update_xaxes(gridcolor=GRID_COLOR, zerolinecolor="#3a3a3a")
        fig.update_yaxes(gridcolor=GRID_COLOR, zerolinecolor="#3a3a3a")

        st.plotly_chart(fig, width='stretch', key="forecast_main_chart")

        # Explanation for forecast chart
        forecast_bullets = []
        if trend_change > 1:
            forecast_bullets.append(f"📈 Based on your past data, <b>{target_col_name}</b> is expected to <b>increase</b> by about {trend_change:.1f}% in the coming period.")
        elif trend_change < -1:
            forecast_bullets.append(f"📉 Based on your past data, <b>{target_col_name}</b> is expected to <b>decrease</b> by about {abs(trend_change):.1f}% in the coming period.")
        else:
            forecast_bullets.append(f"➡️ <b>{target_col_name}</b> is expected to stay roughly the same — no major increase or decrease predicted.")
        forecast_bullets.append("📊 The shaded purple area shows the range of likely values — the actual number will most likely fall somewhere within this band.")
        forecast_bullets.append("📌 The dashed yellow line marks where your real data ends and the prediction begins.")
        _explanation_box("<br>".join(forecast_bullets))

        # ── 2. Trend Decomposition ────────────────────────────────────────
        _section_header("📐 The Big Picture Trend", "Removing short-term ups and downs to reveal the overall direction")

        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(
            x=forecast["ds"],
            y=forecast["trend"],
            mode="lines",
            name="Trend",
            line=dict(color=ACCENT, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(0, 245, 212, 0.08)",
        ))
        fig_trend.update_layout(
            **PLOT_LAYOUT,
            height=350,
            xaxis_title="Date",
            yaxis_title="Trend Value",
            showlegend=False,
        )
        fig_trend.update_xaxes(gridcolor=GRID_COLOR)
        fig_trend.update_yaxes(gridcolor=GRID_COLOR)

        st.plotly_chart(fig_trend, width='stretch', key="forecast_trend_chart")

        # Explanation for trend
        trend_start = forecast["trend"].iloc[0]
        trend_end = forecast["trend"].iloc[-1]
        trend_pct = ((trend_end - trend_start) / abs(trend_start) * 100) if trend_start != 0 else 0
        if trend_pct > 5:
            trend_expl = f"📈 The overall direction of <b>{target_col_name}</b> has been <b>going up</b> over time — this chart strips away the day-to-day noise to show you the big picture."
        elif trend_pct < -5:
            trend_expl = f"📉 The overall direction of <b>{target_col_name}</b> has been <b>going down</b> over time — even though individual values may jump around."
        else:
            trend_expl = f"➡️ The overall direction of <b>{target_col_name}</b> has been <b>relatively flat</b> — no major long-term growth or decline."
        _explanation_box(trend_expl)

        # ── 3. Seasonality Components ─────────────────────────────────────
        _section_header("🌊 Repeating Patterns", "Does your data follow weekly or yearly cycles? This chart reveals those rhythms")

        seasonality_cols = [c for c in forecast.columns if c.startswith("weekly") or c.startswith("yearly")]

        if seasonality_cols:
            fig_season = make_subplots(
                rows=1, cols=len(seasonality_cols),
                subplot_titles=[c.replace("_", " ").title() for c in seasonality_cols],
            )

            colors = [ACCENT, ACCENT_2, "#ff6b6b", "#ffd93d"]
            for idx, col_name in enumerate(seasonality_cols):
                fig_season.add_trace(
                    go.Scatter(
                        x=forecast["ds"],
                        y=forecast[col_name],
                        mode="lines",
                        name=col_name,
                        line=dict(color=colors[idx % len(colors)], width=1.5),
                        showlegend=False,
                    ),
                    row=1, col=idx + 1,
                )

            fig_season.update_layout(
                **PLOT_LAYOUT,
                height=300,
                showlegend=False,
            )
            for annotation in fig_season['layout']['annotations']:
                annotation['font'] = dict(size=13, color=TEXT_WHITE, family="Outfit, Inter, sans-serif")
            fig_season.update_xaxes(gridcolor=GRID_COLOR)
            fig_season.update_yaxes(gridcolor=GRID_COLOR)

            st.plotly_chart(fig_season, width='stretch', key="forecast_seasonality_chart")

            # Explanation for seasonality
            season_expl = "📊 These charts show repeating cycles in your data."
            if "weekly" in str(seasonality_cols):
                season_expl += "<br>📌 <b>Weekly pattern</b> — some days of the week consistently have higher or lower values than others."
            if "yearly" in str(seasonality_cols):
                season_expl += "<br>📌 <b>Yearly pattern</b> — certain months or seasons tend to perform better or worse than others."
            _explanation_box(season_expl)

        # ── 4. Forecast Data Table ────────────────────────────────────────
        _section_header("📋 Forecast Data")

        display_forecast = forecast_future[["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
        display_forecast.columns = ["Date", "Predicted", "Lower Bound", "Upper Bound"]
        for c in ["Predicted", "Lower Bound", "Upper Bound"]:
            display_forecast[c] = display_forecast[c].round(2)
        display_forecast["Date"] = display_forecast["Date"].dt.strftime("%Y-%m-%d")

        with st.expander("📊 View Forecast Table", expanded=False):
            st.dataframe(display_forecast, width='stretch', key="forecast_data_table")

    # ── Navigation ────────────────────────────────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Back to Insights", width='stretch', key="forecast_nav_insights"):
            st.session_state["current_page"] = "Insights"
            st.rerun()
    with col2:
        if st.button("💬 Ask Questions in Chat", width='stretch', key="forecast_nav_chat"):
            st.session_state["current_page"] = "Chat"
            st.rerun()
