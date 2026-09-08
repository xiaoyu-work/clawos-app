"""Run a product's existing tests with its immutable platform dependency."""

import argparse
import os
import subprocess
import sys

from platform_dependency import ROOT, prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", choices=["mail"])
    options = parser.parse_args()
    paths = prepare()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(map(str, [ROOT / "tests", *paths]))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    product = ROOT / "products" / options.product
    tests = [
        product / "apps" / "mail-ai" / "test_main.py",
        product / "extension" / "test_contract.py",
        product / "test_build.py",
        product / "test_extension_package.py",
        ROOT / "tests" / "test_stage.py",
    ]
    subprocess.run([sys.executable, "-m", "pytest", "-q", *map(str, tests)],
                   cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
