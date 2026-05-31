import logging
import os
import re
from pathlib import Path


DEFAULT_MODEL = "llama-3.3-70b-versatile"
PLACEHOLDER_API_KEY = "your_groq_api_key_here"
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
- Do not import or use libraries outside pandas, numpy, plotly, scipy, scikit-learn, and statsmodels.
- Prefer using the injected aliases `pd`, `np`, `px`, and `go` instead of importing libraries.
- Never read or write files.
- Never call print(); assign the final answer to `result`.
- For regression requests, use scikit-learn LinearRegression and compute useful statistics yourself:
  R-squared, adjusted R-squared, MAE, RMSE, intercept, coefficients, feature names, sample size, and target column.
- For regression statistics, store a pandas DataFrame in `result` with metric names and values.
- If the target column is ambiguous, choose the most likely numeric target and include the chosen target in `result`.
- If there are not enough numeric columns for regression, store a clear string in `result` explaining why."""


def generate_code(question: str, df_meta: dict, context_str: str = "") -> str:
    """Generate Python code that answers a natural-language question about the dataset."""
    system_prompt = build_system_prompt(df_meta)
    if context_str:
        system_prompt += "\n\n" + context_str
    return call_llm(system_prompt, question)


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
        return call_llm(system_prompt, f"Explain this to a non-technical person:\n\n{context}")
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
        return call_llm(system_prompt, "Generate the plain-English summary.")
    except Exception as exc:
        logger.warning("Chat explanation generation failed: %s", exc)
        return ""


def generate_data_story(insights_text: str, df_meta: dict) -> str:
    """Generate a ~200-word executive summary narrative from collected insights.

    Args:
        insights_text: All auto-generated insight bullets concatenated as text.
        df_meta: The dataset metadata dict.

    Returns:
        A plain-English narrative paragraph suitable for an executive audience.
    """
    rows = df_meta.get("rows", 0)
    cols = df_meta.get("columns", 0)
    column_list = df_meta.get("column_names", [])
    filename = df_meta.get("filename", "your dataset")

    system_prompt = f"""You are DataTwin's storytelling engine. Your audience is a busy, 
non-technical executive who has 60 seconds to understand this dataset.

Dataset info:
- Name: {filename}
- Size: {rows:,} rows × {cols} columns
- Columns: {column_list}

Here are the key insights already discovered:
{insights_text}

Your task:
1. Write a single, flowing executive summary of approximately 200 words.
2. Structure it as 2-3 short paragraphs — NOT bullet points.
3. Start with a one-sentence overview of what this data is about.
4. Highlight the 3-4 most important findings from the insights.
5. End with a one-sentence recommendation or takeaway.
6. Use ZERO technical jargon — no "correlation", "standard deviation", "skew", "regression".
7. Write in a warm, confident, professional tone — like a trusted analyst briefing a CEO.
8. Return ONLY the narrative text. No headers, no markdown formatting, no code."""

    try:
        return call_llm(system_prompt, "Write the executive data story now.")
    except Exception as exc:
        logger.warning("Data story generation failed: %s", exc)
        return "Unable to generate the data story at this time. Please try again."


def generate_actionable_recommendation(insight_text: str) -> str:
    """Generate an actionable recommendation based on an insight."""
    system_prompt = "You are DataTwin's business strategist."
    user_prompt = f"Based on this data insight: {insight_text}\n\nGive ONE specific actionable recommendation in 1-2 sentences for a non-technical business owner. Be direct and practical. Start with '✅ Action: '"
    try:
        return call_llm(system_prompt, user_prompt)
    except Exception as exc:
        logger.warning("Actionable recommendation generation failed: %s", exc)
        return ""


def generate_followup_questions(question: str, result_summary: str) -> list:
    """Generate exactly 3 specific follow-up questions based on the previous answer."""
    system_prompt = "You are an intelligent data analyst. Return exactly 3 specific follow-up questions as a JSON array of strings. Do not include any other text or markdown formatting."
    user_prompt = f"The user just asked: {question}\nThe answer was: {result_summary}\nSuggest exactly 3 specific follow-up questions they should ask next to go deeper into this analysis. Return only the 3 questions as a JSON array, nothing else."
    try:
        response = call_llm(system_prompt, user_prompt)
        import json
        import re
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return json.loads(response)
    except Exception as exc:
        logger.warning("Failed to generate follow-up questions: %s", exc)
        return []

def standardize_categories(column_name: str, unique_values: list) -> dict:
    """Use the LLM to find and standardize inconsistent categorical values.
    
    Args:
        column_name: The name of the column being analyzed.
        unique_values: A list of unique string values from the column.
        
    Returns:
        A dictionary mapping original messy values to standardized clean values.
    """
    import json
    
    system_prompt = f"""You are an expert data cleaner.
Your job is to fix inconsistent spelling, casing, or punctuation in a categorical column.

Column Name: '{column_name}'
Unique Values: {unique_values}

Rules:
1. Identify values that clearly mean the same thing but are spelled/formatted differently.
   (e.g., "USA", "U.S.A.", "United States" -> map all to "United States")
   (e.g., "apple", "Apple ", "APPLE" -> map all to "Apple")
2. Choose the most common, longest, or most formal-looking version as the standard.
3. Return ONLY a valid JSON dictionary where:
   - The key is the original messy value
   - The value is the standardized clean value
4. Only include values in the JSON that actually need changing. If a value is fine, you can omit it.
5. Do NOT include markdown code blocks (```json) in your response, just the raw JSON text.
6. If no standardizations are needed, return an empty dictionary: {{}}"""

    try:
        response_text = call_llm(system_prompt, "Return the JSON mapping.")
        # Strip potential markdown fences just in case
        response_text = response_text.replace("```json", "").replace("```", "").strip()
        mapping = json.loads(response_text)
        if isinstance(mapping, dict):
            return mapping
    except Exception as exc:
        logger.warning("Failed to standardize categories for %s: %s", column_name, exc)
    
    return {}


def call_llm(system_prompt: str, user_question: str) -> str:
    """Call the LLM with the DataTwin prompt and return raw executable Python code."""
    try:
        from dotenv import load_dotenv
        from groq import Groq

        load_dotenv(PROJECT_ROOT / ".env", override=True)
        api_key = _get_api_key()

        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_question},
            ],
            temperature=0,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty response.")

        code = _strip_markdown_code_fence(content)
        if not code:
            raise ValueError("LLM returned an empty code response.")

        return code
    except Exception as exc:
        logger.exception("LLM code generation failed.")
        raise RuntimeError("AI is temporarily unavailable. Please try again.") from exc


def call_openai(system_prompt: str, user_question: str) -> str:
    """Backward-compatible alias for older imports; calls LLM."""
    return call_llm(system_prompt, user_question)


def call_gemini(system_prompt: str, user_question: str) -> str:
    """Backward-compatible alias for older imports; calls LLM."""
    return call_llm(system_prompt, user_question)


def _get_api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == PLACEHOLDER_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured.")
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
