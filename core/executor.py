import ast
import logging
import queue
import threading

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

logger = logging.getLogger(__name__)
ALLOWED_IMPORTS = {
    "pandas", "numpy", "plotly", "scipy", "sklearn",
    # Safe standard library modules commonly needed for data analysis
    "ast", "math", "re", "json", "collections", "itertools",
    "functools", "statistics", "datetime", "decimal", "operator",
}

def is_safe_code(code: str) -> bool:
    """Parse the Python code using AST to check for security violations or unsafe operations."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        logger.warning("Code is syntax-invalid, failed safety parsing.")
        return False

    blocked_modules = {
        "os", "sys", "subprocess", "shutil", "socket", "urllib", "requests",
        "builtins", "ctypes", "pty", "platform", "multiprocessing", "threading",
        "webbrowser", "pathlib", "importlib", "gc", "pdb"
    }
    blocked_functions = {
        "open", "exec", "eval", "compile", "__import__", "quit", "exit",
        "getattr", "setattr", "delattr"
    }
    blocked_attributes = {
        "__globals__", "__code__", "__subclasses__", "__builtins__",
        "func_globals", "func_code"
    }

    for node in ast.walk(tree):
        # 1. Check direct imports (e.g. import os)
        if isinstance(node, ast.Import):
            for alias in node.names:
                base_name = alias.name.split('.')[0]
                if base_name in blocked_modules or base_name not in ALLOWED_IMPORTS:
                    logger.warning("Blocked import detected: %s", alias.name)
                    return False

        # 2. Check import-from imports (e.g. from os import system)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base_name = node.module.split('.')[0]
                if base_name in blocked_modules or base_name not in ALLOWED_IMPORTS:
                    logger.warning("Blocked import from detected: %s", node.module)
                    return False

        # 3. Check function calls (e.g. open('file.txt'))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in blocked_functions:
                    logger.warning("Blocked function call detected: %s", node.func.id)
                    return False

        # 4. Check dangerous attribute access (e.g. obj.__class__)
        elif isinstance(node, ast.Attribute):
            if node.attr in blocked_attributes:
                logger.warning("Blocked attribute access detected: %s", node.attr)
                return False

    return True

def get_result_type(result) -> str:
    """Detect the data type of the execution result for appropriate UI rendering."""
    if isinstance(result, go.Figure):
        return "chart"
    elif isinstance(result, (pd.DataFrame, pd.Series)):
        return "table"
    else:
        return "text"

def execute_code(code: str, df: pd.DataFrame) -> dict:
    """Safely execute generated Python code and return formatted result or error.
    
    Returns:
        dict: {"type": "chart"|"table"|"text"|"error", "data": result}
    """
    if not is_safe_code(code):
        return {
            "type": "error",
            "data": "Security violation: Dangerous code pattern detected."
        }

    result_queue = queue.Queue()

    def run_target():
        try:
            # We rely on our static AST analysis (is_safe_code) to block dangerous constructs 
            # before execution, while letting standard builtins function normally at runtime 
            # to prevent library import errors.
            exec_globals = {
                "pd": pd,
                "np": np,
                "px": px,
                "go": go,
                "df": df,
            }
            exec_locals = {}
            
            exec(code, exec_globals, exec_locals)
            
            result = None
            if "result" in exec_locals:
                result = exec_locals["result"]
            elif "result" in exec_globals:
                result = exec_globals["result"]
            else:
                raise ValueError("The variable 'result' was not defined in the code.")
                
            result_queue.put((True, result))
        except Exception as exc:
            result_queue.put((False, exc))

    t = threading.Thread(target=run_target)
    t.daemon = True
    t.start()
    t.join(timeout=30.0)

    if t.is_alive():
        return {
            "type": "error",
            "data": "Execution timed out. The code took longer than 30 seconds to run."
        }

    if result_queue.empty():
        return {
            "type": "error",
            "data": "Execution failed: No result was returned."
        }

    success, val = result_queue.get()
    if not success:
        logger.exception("Error executing generated code")
        return {
            "type": "error",
            "data": f"I couldn't compute that. Try rephrasing your question. (Error: {val})"
        }

    try:
        res_type = get_result_type(val)
        return {"type": res_type, "data": val}
    except Exception as exc:
        logger.exception("Error formatting execution result")
        return {
            "type": "error",
            "data": f"Failed to parse result: {exc}"
        }
