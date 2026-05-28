import logging
import os
import re
from pathlib import Path


DEFAULT_MODEL = "gemini-2.5-flash"
PLACEHOLDER_API_KEY = "your_gemini_api_key_here"
logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_system_prompt(df_meta: dict) -> str:
    """Build the system prompt that tells Gemini how to answer with Python code only."""
    rows = df_meta.get("rows", 0)
    cols = df_meta.get("columns", 0)
    column_list = df_meta.get("column_names", [])
    dtypes = df_meta.get("dtypes", {})
    sample = df_meta.get("sample", [])

    return f"""You are DataTwin's code generation engine.

The user has uploaded a dataset with the following properties:
- Shape: {rows} rows, {cols} columns
- Columns: {column_list}
- Column types: {dtypes}
- Sample data (first 3 rows): {sample}

Your job:
1. Understand the user's question
2. Write Python code using only pandas, numpy, plotly, scipy, and scikit-learn to answer it
3. The DataFrame is already loaded as variable `df`
4. Store the final answer in a variable called `result`
5. If the answer is a chart, make it a plotly figure
6. If the answer is a number or text, make it a string
7. If the answer is tabular, keep it as a DataFrame
8. Return ONLY raw Python code. No markdown. No explanation. No triple backticks.

Rules:
- Do not import or use libraries outside pandas, numpy, plotly, scipy, and scikit-learn.
- Do not use statsmodels. It is not installed.
- Prefer using the injected aliases `pd`, `np`, `px`, and `go` instead of importing libraries.
- Never read or write files.
- Never call print(); assign the final answer to `result`.
- For regression requests, use scikit-learn LinearRegression and compute useful statistics yourself:
  R-squared, adjusted R-squared, MAE, RMSE, intercept, coefficients, feature names, sample size, and target column.
- For regression statistics, store a pandas DataFrame in `result` with metric names and values.
- If the target column is ambiguous, choose the most likely numeric target and include the chosen target in `result`.
- If there are not enough numeric columns for regression, store a clear string in `result` explaining why."""


def generate_code(question: str, df_meta: dict) -> str:
    """Generate Python code that answers a natural-language question about the dataset."""
    system_prompt = build_system_prompt(df_meta)
    return call_gemini(system_prompt, question)


def generate_explanation(context: str, df_meta: dict) -> str:
    """Generate a plain-English explanation of a chart or analysis result.

    Args:
        context: A string describing what the chart/table shows (e.g. correlation values,
                 distribution stats, forecast metrics).
        df_meta: The dataset metadata dict for additional context.

    Returns:
        A markdown-formatted string with 3-5 bullet points in non-technical language.
    """
    column_list = df_meta.get("column_names", [])

    system_prompt = f"""You are DataTwin's explanation engine. Your audience is non-technical: 
business owners, students, and professionals who have NEVER heard terms like 
"correlation", "distribution", "variance", or "outliers".

The user's dataset has columns: {column_list}

Rules:
1. Write 3-5 bullet points explaining what the data means in PLAIN ENGLISH.
2. Start each bullet with an emoji (✅, ⚠️, 📌, 💡, 📊).
3. NEVER use technical jargon. If you must reference a concept, explain it in brackets.
   Bad: "The Pearson correlation coefficient is 0.85"
   Good: "✅ Sales and Marketing Spend are strongly connected — when one goes up, the other usually goes up too"
4. Every bullet must answer "So what does this mean for me?" from a business perspective.
5. Keep it under 5 bullets. Do not overwhelm the user.
6. Return ONLY the bullet points as markdown. No headers, no intro text, no code."""

    try:
        return call_gemini(system_prompt, f"Explain this to a non-technical person:\n\n{context}")
    except Exception as exc:
        logger.warning("Explanation generation failed: %s", exc)
        return ""


def generate_chat_explanation(question: str, result_summary: str, df_meta: dict) -> str:
    """Generate a 'What This Means' explanation for chat responses.

    Args:
        question: The original user question.
        result_summary: A text summary of the result (chart data, table, or text).
        df_meta: The dataset metadata dict.

    Returns:
        Markdown-formatted bullet points for the "What This Means For You" section.
    """
    column_list = df_meta.get("column_names", [])

    system_prompt = f"""You are DataTwin's insight summarizer. Your audience is NON-TECHNICAL:
business owners, students, and professionals.

The user's dataset has columns: {column_list}

The user asked: "{question}"
The analysis produced these results:
{result_summary}

Rules:
1. Write 3-5 bullet points summarizing the KEY FINDINGS in plain English.
2. Start each bullet with an emoji (✅, ⚠️, 📌, 💡, 📊).
3. NEVER use technical words like "correlation", "coefficient", "variance", "statistically significant", "regression".
   Instead, say things like "strongly connected", "tends to go up together", "no clear pattern".
4. Every bullet must answer "So what does this mean for me?" from a business perspective.
5. Keep each bullet to 1-2 sentences max.
6. Return ONLY the bullet points as markdown text. No headers, no intro, no code."""

    try:
        return call_gemini(system_prompt, "Generate the plain-English summary.")
    except Exception as exc:
        logger.warning("Chat explanation generation failed: %s", exc)
        return ""


def call_gemini(system_prompt: str, user_question: str) -> str:
    """Call Gemini with the DataTwin prompt and return raw executable Python code."""
    try:
        from dotenv import load_dotenv
        from google import genai
        from google.genai import types

        load_dotenv(PROJECT_ROOT / ".env", override=True)
        api_key = _get_api_key()

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=user_question,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
            ),
        )

        content = getattr(response, "text", None)
        if not content:
            raise ValueError("Gemini returned an empty response.")

        code = _strip_markdown_code_fence(content)
        if not code:
            raise ValueError("Gemini returned an empty code response.")

        return code
    except Exception as exc:
        logger.exception("Gemini code generation failed.")
        raise RuntimeError("AI is temporarily unavailable. Please try again.") from exc


def call_openai(system_prompt: str, user_question: str) -> str:
    """Backward-compatible alias for older imports; calls Gemini."""
    return call_gemini(system_prompt, user_question)


def _get_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == PLACEHOLDER_API_KEY:
        raise ValueError("GEMINI_API_KEY is not configured.")
    return api_key


def _strip_markdown_code_fence(content: str) -> str:
    stripped = content.strip()
    fenced_match = re.search(r"```(?:python|py)?\s*(.*?)```", stripped, flags=re.DOTALL)

    if fenced_match:
        return fenced_match.group(1).strip()

    opening_fence_match = re.match(r"```(?:python|py)?\s*(.*)", stripped, flags=re.DOTALL)
    if opening_fence_match:
        return opening_fence_match.group(1).strip()

    return stripped
