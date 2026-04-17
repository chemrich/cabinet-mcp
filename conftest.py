"""Root conftest — add src/ to sys.path for editable-style imports."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))
