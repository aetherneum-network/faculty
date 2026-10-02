import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))
from app import add  # noqa: E402

sys.exit(0 if add(20, 22) == 42 else 1)
