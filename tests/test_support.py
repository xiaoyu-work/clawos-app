"""Isolated loading for product modules that are executable entry points."""

import importlib.util
import sys


def load_local_module(path, name):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module
