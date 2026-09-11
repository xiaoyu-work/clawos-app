from types import SimpleNamespace

import pytest

from test_support import configure_development_platform, platform_dependency


def pytest_addoption(parser):
    parser.addoption(
        "--platform-artifact-fixture",
        help="Explicit local OS-built artifact for the real SDK interoperability test; never a production override",
    )
    parser.addoption("--development-platform", help="Explicit local development platform archive")
    parser.addoption("--development-platform-version", help="Expected local archive version")
    parser.addoption("--development-platform-sha256", help="Expected local archive SHA-256")


def pytest_configure(config):
    options = SimpleNamespace(**{
        name: config.getoption(name)
        for name in (
            "development_platform", "development_platform_version", "development_platform_sha256",
        )
    })
    try:
        development = platform_dependency().development_from_args(options)
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error
    configure_development_platform(
        None if development is None else (
            development.archive, development.version, development.sha256,
        )
    )


def pytest_unconfigure(config):
    configure_development_platform(None)
