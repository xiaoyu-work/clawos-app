"""Compatibility entry point for the shared native product builder."""

from functools import partial
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import native_build

prepare = partial(native_build.prepare, "calendar")

if __name__ == "__main__":
    native_build.main("calendar")
