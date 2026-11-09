#!/usr/bin/env python3
"""Compatibility launcher for the versioned OS browser transport."""

import os
import sys


if __name__ == "__main__":
    os.execv(
        "/usr/bin/python3",
        ["/usr/bin/python3", "-I", "/usr/lib/cos/browser-native-host.py", *sys.argv[1:]],
    )
