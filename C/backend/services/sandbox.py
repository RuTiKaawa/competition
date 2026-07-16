import subprocess
import sys
import tempfile
import os
import logging

logger = logging.getLogger(__name__)

SANDBOX_TIMEOUT = 10

ALLOWED_MODULES = {
    "pandas", "numpy", "sklearn", "matplotlib",
    "math", "statistics", "json", "csv", "datetime",
    "collections", "itertools", "functools", "operator",
    "random", "re", "string", "decimal", "fractions",
    "typing", "dataclasses", "enum", "copy",
}

FORBIDDEN_KEYWORDS = [
    "import os", "import sys", "import subprocess", "import shutil",
    "import socket", "import requests", "import urllib",
    "__import__", "exec(", "eval(", "compile(",
    "open(", "file(", "input(",
    "globals()", "locals()", "getattr(", "setattr(", "