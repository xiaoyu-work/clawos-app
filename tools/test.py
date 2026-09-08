"""Run a product's existing tests with its immutable platform dependency."""

import argparse
import json
import os
import subprocess
import sys

from platform_dependency import ROOT, prepare
from stage import products


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", nargs="+", choices=products())
    options = parser.parse_args()
    paths = prepare()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(map(str, [ROOT / "tests", *paths]))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    tests = []
    for name in options.product:
        product = ROOT / "products" / name
        package = json.loads((product / "package.json").read_text())
        tests.extend(product / app / "test_main.py" for app in package["apps"])
        tests.extend(product / test for test in package["tests"])
    tests.extend([
        ROOT / "tests" / "test_stage.py",
        ROOT / "tests" / "test_platform_dependency.py",
    ])
    subprocess.run([sys.executable, "-m", "pytest", "-q", "--import-mode=importlib", *map(str, tests)],
                   cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
