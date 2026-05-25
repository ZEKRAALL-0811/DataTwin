import logging
import os
import re


DEFAULT_MODEL = "gpt-4o"
PLACEHOLDER_API_KEY = "your_openai_api_key_here"
logger = logging.getLogger(__name__)


def build_system_prompt(df_meta: dict) -> str:
    """Build the system prompt that tells OpenAI how to answer with Python code only."""
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
2. Write Python code using pandas and plotly to answer it
3. The DataFrame is already loaded as variable `df`
4. Store the final answer in a variable called `result`
5. If the answer is a chart, make it a plotly figure
6. If the answer is a number or text, make it a string
7. If the answer is tabular, keep it as a DataFrame
8. Return ONLY raw Python code. No markdown. No explanation. No triple backticks."""


def call_openai(system_prompt: str, user_question: str) -> str:
    """Call OpenAI with the DataTwin prompt and return raw executable Python code."""
    try:
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv()
        api_key = _get_api_key()

        client = OpenAI(api_key=api_key)
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
            raise ValueError("OpenAI returned an empty response.")

        code = _strip_markdown_code_fence(content)
        if not code:
            raise ValueError("OpenAI returned an empty code response.")

        return code
    except Exception as exc:
        logger.exception("OpenAI code generation failed.")
        raise RuntimeError("AI is temporarily unavailable. Please try again.") from exc


def generate_code(question: str, df_meta: dict) -> str:
    """Generate Python code that answers a natural-language question about the dataset."""
    system_prompt = build_system_prompt(df_meta)
    return call_openai(system_prompt, question)


def _get_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == PLACEHOLDER_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")
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
