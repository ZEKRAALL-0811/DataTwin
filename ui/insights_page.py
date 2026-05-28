import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import logging

logger = logging.getLogger(__name__)

# ── Design Tokens ────────────────────────────────────────────────────────────
ACCENT = "#00f5d4"
BG_CARD = "#1a1a1a"
BG_PLOT = "#1a1a1a"
TEXT_MUTED = "#a0a0a0"
TEXT_WHITE = "#ffffff"
GRID_COLOR = "#2c2c2c"
PALETTE = ["#00f5d4", "#7b61ff", "#ff6b6b", "#ffd93d", "#6bcb77",
           "#4fc3f7", "#ff8a65", "#ce93d8", "#80cbc4", "#fff176"]

PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor=BG_PLOT,
    plot_bgcolor=BG_PLOT,
    font=dict(color=TEXT_WHITE, family="Outfit, Inter, sans-serif", size=12),
    margin=dict(l=40, r=40, t=50, b=40),
    hoverlabel=dict(bgcolor="#2a2a2a", font_size=13, font_family="Outfit, Inter, sans-serif"),
)


def _section_header(title: str, subtitle: str = ""):
    """Render a styled section header."""
    html = f"""
    <div style="margin-top: 2rem; margin-bottom: 1rem;">
        <h3 style="color: {ACCENT}; font-weight: 700; margin-bottom: 0.2rem;">{title}</h3>
        {"<p style='color: " + TEXT_MUTED + "; font-size: 0.9rem; margin-top: 0;'>" + subtitle + "</p>" if subtitle else ""}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _stat_card(label: str, value: str, icon: str = ""):
    """Render a single metric card with glassmorphism style."""
    return f"""
    <div style="
        background: linear-gradient(135deg, #1a1a1a 0%, #222222 100%);
        border: 1px solid #2a2a2a;
        border-radius: 12px;
        padding: 18px;
        text-align: center;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    ">
        <div style="font-size: 1.4rem; margin-bottom: 4px;">{icon}</div>
        <div style="color: {ACCENT}; font-size: 1.6rem; font-weight: 700;">{value}</div>
        <div style="color: {TEXT_MUTED}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 4px;">{label}</div>
    </div>
    """


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


def _build_stats_explanation(desc: pd.DataFrame, num_cols: list) -> str:
    """Build a plain-English explanation of summary statistics."""
    bullets = []
    if len(num_cols) > 0:
        # Find the column with the biggest range
        ranges = {}
        for col in desc.index:
            try:
                col_min = float(desc.loc[col, "Min"])
                col_max = float(desc.loc[col, "Max"])
                ranges[col] = col_max - col_min
            except (ValueError, TypeError):
                pass

        if ranges:
            widest = max(ranges, key=ranges.get)
            bullets.append(f"📊 <b>{widest}</b> has the widest range of values — it varies the most across your data.")

        # Find column with highest average
        means = {}
        for col in desc.index:
            try:
                means[col] = float(desc.loc[col, "Mean"])
            except (ValueError, TypeError):
                pass

        if means:
            highest_avg = max(means, key=means.get)
            bullets.append(f"📌 <b>{highest_avg}</b> has the highest average value ({means[highest_avg]:,.1f}).")

        # Check for skewed columns
        for col in desc.index:
            try:
                skew_val = float(desc.loc[col, "Skew"])
                if abs(skew_val) > 1.5:
                    direction = "higher" if skew_val > 0 else "lower"
                    bullets.append(f"⚠️ <b>{col}</b> is lopsided — most values cluster on the {direction} end, with a few extreme values on the other side.")
                    break
            except (ValueError, TypeError):
                pass

    if not bullets:
        bullets.append("📊 This table shows the basic number facts (average, smallest, largest) for each column in your data.")

    return "<br>".join(bullets)


def _build_distribution_explanation(df: pd.DataFrame, display_cols: list) -> str:
    """Build a plain-English explanation of distribution histograms."""
    bullets = []
    bullets.append("📊 Each bar chart below shows how your values are spread out — tall bars mean lots of data points at that value.")

    for col_name in display_cols[:3]:
        series = df[col_name].dropna()
        if len(series) == 0:
            continue
        median_val = series.median()
        mean_val = series.mean()
        if abs(mean_val - median_val) > 0.3 * series.std() and series.std() > 0:
            bullets.append(f"⚠️ <b>{col_name}</b> is not evenly spread — it's pulled toward one side, meaning a few unusually high or low values are shifting the average.")
            break

    if len(bullets) == 1:
        bullets.append(f"✅ Your numeric columns are fairly evenly spread, with no major surprises in how the values are distributed.")

    return "<br>".join(bullets)


def _build_correlation_explanation(corr: pd.DataFrame) -> str:
    """Build a plain-English explanation of the correlation matrix."""
    bullets = []
    bullets.append("📊 This color grid shows which columns move together. Bright teal = they rise and fall together. Purple = when one goes up, the other goes down.")

    # Find strongest positive correlation
    strong_pos = []
    strong_neg = []
    weak = []

    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            val = corr.iloc[i, j]
            pair = (corr.columns[i], corr.columns[j], val)
            if abs(val) >= 0.7:
                if val > 0:
                    strong_pos.append(pair)
                else:
                    strong_neg.append(pair)
            elif abs(val) < 0.2:
                weak.append(pair)

    if strong_pos:
        best = max(strong_pos, key=lambda x: x[2])
        bullets.append(f"✅ <b>{best[0]}</b> and <b>{best[1]}</b> are strongly connected — when one goes up, the other usually goes up too.")

    if strong_neg:
        worst = min(strong_neg, key=lambda x: x[2])
        bullets.append(f"⚠️ <b>{worst[0]}</b> and <b>{worst[1]}</b> move in opposite directions — when one increases, the other tends to decrease.")

    if weak and len(bullets) < 4:
        w = weak[0]
        bullets.append(f"📌 <b>{w[0]}</b> and <b>{w[1]}</b> have almost no relationship — they seem to be independent of each other.")

    if not strong_pos and not strong_neg:
        bullets.append("📌 None of your columns are strongly connected to each other — they each seem to tell their own story.")

    return "<br>".join(bullets)


def _build_missing_explanation(missing_df: pd.DataFrame, total_missing: int, total_cells: int) -> str:
    """Build a plain-English explanation of missing values."""
    bullets = []
    pct = (total_missing / total_cells * 100) if total_cells else 0

    if pct < 1:
        bullets.append(f"✅ Your data is almost perfectly complete — only {pct:.1f}% of cells are empty. This is excellent!")
    elif pct < 10:
        bullets.append(f"⚠️ About {pct:.1f}% of your data has gaps. This is manageable but worth noting.")
    else:
        bullets.append(f"🚨 {pct:.1f}% of your data is missing. This could affect the accuracy of any analysis.")

    if len(missing_df) > 0:
        worst_col = missing_df.iloc[-1]
        bullets.append(f"📌 <b>{worst_col['Column']}</b> has the most gaps ({worst_col['Percent']:.1f}% empty). Consider whether this column is essential for your analysis.")

    return "<br>".join(bullets)


def _build_categorical_explanation(df: pd.DataFrame, cat_cols: list) -> str:
    """Build a plain-English explanation of categorical breakdowns."""
    bullets = []
    bullets.append("📊 These charts show the most common categories (text values) in your data and how often each one appears.")

    for col_name in cat_cols[:2]:
        vc = df[col_name].value_counts()
        if len(vc) > 0:
            top_val = vc.index[0]
            top_pct = (vc.iloc[0] / len(df) * 100)
            bullets.append(f"📌 In <b>{col_name}</b>, the most common value is \"<b>{top_val}</b>\" — it appears in {top_pct:.0f}% of your data.")

    return "<br>".join(bullets)


def _build_outlier_explanation(df: pd.DataFrame, box_cols: list) -> str:
    """Build a plain-English explanation of outlier detection."""
    bullets = []
    bullets.append("📊 These box charts show the normal range of each column. Dots outside the boxes are unusual values (much higher or lower than typical).")

    for col_name in box_cols[:3]:
        series = df[col_name].dropna()
        if len(series) == 0:
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        outlier_count = ((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum()
        if outlier_count > 0:
            bullets.append(f"⚠️ <b>{col_name}</b> has {outlier_count:,} unusual values that are much higher or lower than the rest. These might be data entry errors or genuinely extreme cases.")
            break

    if len(bullets) == 1:
        bullets.append("✅ No major unusual values were found — your data looks consistent.")

    return "<br>".join(bullets)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN RENDER
# ═════════════════════════════════════════════════════════════════════════════
def render_insights_page():
    """Auto-generate a full insights dashboard from the uploaded dataset."""
    if st.session_state.get("df") is None:
        st.session_state["current_page"] = "Upload"
        st.rerun()
        return

    df: pd.DataFrame = st.session_state["df"]
    meta: dict = st.session_state["df_meta"]

    st.markdown(
        f"""
        <div style="margin-bottom: 1.5rem;">
            <h2 style="color: {ACCENT}; font-weight: 700; margin-bottom: 0.2rem;">🔍 Auto-Generated Insights</h2>
            <p style="color: {TEXT_MUTED}; font-size: 0.95rem;">
                Your DataTwin analyzed <strong style="color:{TEXT_WHITE}">{meta['rows']:,}</strong> rows × 
                <strong style="color:{TEXT_WHITE}">{meta['columns']}</strong> columns and produced these insights automatically.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 1. Quick Stats Cards ─────────────────────────────────────────────────
    num_cols = meta.get("numeric_columns", [])
    cat_cols = meta.get("categorical_columns", [])
    date_cols = meta.get("datetime_columns", [])
    total_missing = sum(meta["missing_values"].values())
    total_cells = meta["rows"] * meta["columns"]
    completeness = ((total_cells - total_missing) / total_cells * 100) if total_cells else 0

    cols = st.columns(5)
    cards = [
        ("Rows", f"{meta['rows']:,}", "📊"),
        ("Columns", str(meta['columns']), "📋"),
        ("Numeric", str(len(num_cols)), "🔢"),
        ("Categorical", str(len(cat_cols)), "🏷️"),
        ("Completeness", f"{completeness:.1f}%", "✅"),
    ]
    for col, (label, value, icon) in zip(cols, cards):
        with col:
            st.markdown(_stat_card(label, value, icon), unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)

    # ── 2. Summary Statistics Table ──────────────────────────────────────────
    if num_cols:
        _section_header("📐 Summary Statistics", "A quick snapshot of your number columns — averages, smallest/largest values, and more")

        desc = df[num_cols].describe().T
        desc["median"] = df[num_cols].median()
        desc["skew"] = df[num_cols].skew()
        desc = desc[["count", "mean", "std", "min", "25%", "median", "75%", "max", "skew"]]
        desc.columns = ["Count", "Mean", "Std Dev", "Min", "25%", "Median", "75%", "Max", "Skew"]

        # Round for display
        for c in desc.columns:
            desc[c] = desc[c].apply(lambda x: round(x, 2) if isinstance(x, float) else x)

        st.dataframe(desc, width='stretch')
        _explanation_box(_build_stats_explanation(desc, num_cols))

    # ── 3. Distribution Histograms ───────────────────────────────────────────
    if num_cols:
        _section_header("📈 Value Spread", "How your numbers are distributed — where most values fall and where the extremes are")

        # Show up to 6 columns at a time in a 2-column grid
        display_cols = num_cols[:8]
        n_charts = len(display_cols)
        n_rows_grid = (n_charts + 1) // 2

        fig = make_subplots(
            rows=n_rows_grid, cols=2,
            subplot_titles=[c for c in display_cols],
            vertical_spacing=0.08,
            horizontal_spacing=0.08,
        )

        for idx, col_name in enumerate(display_cols):
            row = idx // 2 + 1
            col_pos = idx % 2 + 1
            series = df[col_name].dropna()

            fig.add_trace(
                go.Histogram(
                    x=series,
                    name=col_name,
                    marker_color=PALETTE[idx % len(PALETTE)],
                    opacity=0.85,
                    showlegend=False,
                ),
                row=row, col=col_pos,
            )

        fig.update_layout(
            **PLOT_LAYOUT,
            height=300 * n_rows_grid,
            title_text=None,
            showlegend=False,
        )
        fig.update_xaxes(gridcolor=GRID_COLOR, zerolinecolor="#3a3a3a")
        fig.update_yaxes(gridcolor=GRID_COLOR, zerolinecolor="#3a3a3a")

        # Style subplot titles
        for annotation in fig['layout']['annotations']:
            annotation['font'] = dict(size=13, color=TEXT_WHITE, family="Outfit, Inter, sans-serif")

        st.plotly_chart(fig, width='stretch')
        _explanation_box(_build_distribution_explanation(df, display_cols))

    # ── 4. Correlation Heatmap ───────────────────────────────────────────────
    if len(num_cols) >= 2:
        _section_header("🔗 How Your Columns Relate", "This map shows which columns tend to move together — bright colors mean a strong connection")

        corr = df[num_cols].corr()

        fig_corr = px.imshow(
            corr,
            text_auto=".2f",
            color_continuous_scale=["#7b61ff", "#1a1a1a", "#00f5d4"],
            aspect="auto",
        )
        fig_corr.update_layout(
            **PLOT_LAYOUT,
            height=max(400, 50 * len(num_cols)),
            coloraxis_colorbar=dict(
                title=dict(text="r", font=dict(color=TEXT_MUTED)),
                tickfont=dict(color=TEXT_MUTED),
            ),
        )
        st.plotly_chart(fig_corr, width='stretch')
        _explanation_box(_build_correlation_explanation(corr))

    # ── 5. Missing Values ────────────────────────────────────────────────────
    if total_missing > 0:
        _section_header("⚠️ Data Gaps", "Some cells in your dataset are empty — here's where the gaps are")

        missing_df = pd.DataFrame({
            "Column": list(meta["missing_values"].keys()),
            "Missing": list(meta["missing_values"].values()),
            "Percent": [meta["missing_percentages"][c] for c in meta["missing_values"]],
        })
        missing_df = missing_df[missing_df["Missing"] > 0].sort_values("Missing", ascending=True)

        fig_miss = go.Figure()
        fig_miss.add_trace(go.Bar(
            y=missing_df["Column"],
            x=missing_df["Percent"],
            orientation="h",
            marker=dict(
                color=missing_df["Percent"],
                colorscale=[[0, "#00f5d4"], [0.5, "#ffd93d"], [1.0, "#ff6b6b"]],
                line=dict(width=0),
            ),
            text=[f"{v:.1f}%" for v in missing_df["Percent"]],
            textposition="outside",
            textfont=dict(color=TEXT_MUTED, size=11),
            hovertemplate="<b>%{y}</b><br>Missing: %{x:.1f}%<extra></extra>",
        ))
        fig_miss.update_layout(
            **PLOT_LAYOUT,
            height=max(300, 28 * len(missing_df)),
            xaxis_title="Missing %",
            yaxis_title=None,
            showlegend=False,
        )
        fig_miss.update_xaxes(gridcolor=GRID_COLOR, range=[0, max(missing_df["Percent"]) * 1.3])
        fig_miss.update_yaxes(gridcolor=GRID_COLOR)

        st.plotly_chart(fig_miss, width='stretch')
        _explanation_box(_build_missing_explanation(missing_df, total_missing, total_cells))
    else:
        _section_header("✅ No Data Gaps", "Your dataset is 100% complete — every cell has a value!")
        _explanation_box("✅ Great news! Your data has zero gaps. Every single cell is filled in, which means any analysis will be working with the full picture.")

    # ── 6. Categorical Breakdowns ────────────────────────────────────────────
    if cat_cols:
        _section_header("🏷️ Most Common Categories", "How often each category appears in your text-based columns")

        # Show up to 4 categorical columns, 2 per row
        display_cats = cat_cols[:4]

        for row_start in range(0, len(display_cats), 2):
            row_cats = display_cats[row_start:row_start + 2]
            chart_cols = st.columns(len(row_cats))

            for idx, col_name in enumerate(row_cats):
                with chart_cols[idx]:
                    value_counts = df[col_name].value_counts().head(10)
                    color_idx = row_start + idx

                    fig_cat = go.Figure()
                    fig_cat.add_trace(go.Bar(
                        x=value_counts.values,
                        y=value_counts.index.astype(str),
                        orientation="h",
                        marker_color=PALETTE[color_idx % len(PALETTE)],
                        opacity=0.9,
                        text=value_counts.values,
                        textposition="outside",
                        textfont=dict(color=TEXT_MUTED, size=11),
                        hovertemplate="<b>%{y}</b><br>Count: %{x:,}<extra></extra>",
                    ))
                    fig_cat.update_layout(
                        **PLOT_LAYOUT,
                        title=dict(text=col_name, font=dict(size=14, color=ACCENT)),
                        height=max(280, 30 * len(value_counts)),
                        showlegend=False,
                        xaxis_title="Count",
                        yaxis=dict(autorange="reversed"),
                    )
                    fig_cat.update_xaxes(gridcolor=GRID_COLOR)
                    fig_cat.update_yaxes(gridcolor=GRID_COLOR)

                    st.plotly_chart(fig_cat, width='stretch', key=f"cat_{col_name}")

        _explanation_box(_build_categorical_explanation(df, display_cats))

    # ── 7. Outlier Detection (Bonus) ─────────────────────────────────────────
    if num_cols:
        _section_header("🎯 Unusual Values", "Spots values that are much higher or lower than normal — potential errors or interesting extremes")

        box_cols = num_cols[:6]
        fig_box = go.Figure()

        for idx, col_name in enumerate(box_cols):
            fig_box.add_trace(go.Box(
                y=df[col_name].dropna(),
                name=col_name,
                marker_color=PALETTE[idx % len(PALETTE)],
                boxmean="sd",
                line=dict(width=1.5),
            ))

        fig_box.update_layout(
            **PLOT_LAYOUT,
            height=450,
            showlegend=False,
            yaxis_title="Value",
        )
        fig_box.update_xaxes(gridcolor=GRID_COLOR)
        fig_box.update_yaxes(gridcolor=GRID_COLOR)

        st.plotly_chart(fig_box, width='stretch')
        _explanation_box(_build_outlier_explanation(df, box_cols))

    # ── Navigation ───────────────────────────────────────────────────────────
    st.markdown("<br/>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💬 Ask Questions in Chat", width='stretch'):
            st.session_state["current_page"] = "Chat"
            st.rerun()
    with col2:
        if st.button("🔮 Forecast Trends", width='stretch'):
            st.session_state["current_page"] = "Forecast"
            st.rerun()
