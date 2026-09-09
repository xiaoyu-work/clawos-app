"""Run declared App source tests with their immutable platform and library dependencies."""

import argparse
import os
import subprocess
import sys

from platform_dependency import ROOT, prepare
from stage import app_entries, load_package, python_libraries


def source_tests(source, package):
    declared = [source / path for path in package["tests"]]
    automatic = []
    for app in app_entries(source, package).values():
        default = app / "test_main.py"
        if default.is_file():
            automatic.append(default)
        elif not any(path.is_file() and path.resolve().is_relative_to(app.resolve()) for path in declared):
            raise ValueError(f"App without test_main.py requires an explicit test file: {app}")
    return list(dict.fromkeys([*automatic, *declared]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", nargs="*")
    parser.add_argument("--capability", nargs="+", default=[])
    options = parser.parse_args()
    if not options.product and not options.capability:
        parser.error("select at least one product or --capability source group")
    packages = [
        *(load_package(name) for name in options.product),
        *(load_package(name, "capability") for name in options.capability),
    ]
    paths = prepare()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    tests = []
    for product, package in packages:
        apps = app_entries(product, package)
        paths.extend(path.parent for path in python_libraries(product, package, list(apps)).values())
        tests.extend(source_tests(product, package))
    env["PYTHONPATH"] = os.pathsep.join(map(str, dict.fromkeys([ROOT / "tests", *paths])))
    tests.extend([
        ROOT / "tests" / "test_stage.py",
        ROOT / "tests" / "test_platform_dependency.py",
    ])
    subprocess.run([sys.executable, "-m", "pytest", "-q", "--import-mode=importlib", *map(str, tests)],
                   cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
