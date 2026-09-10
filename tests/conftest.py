def pytest_addoption(parser):
    parser.addoption(
        "--platform-artifact-fixture",
        help="Explicit local OS-built artifact for the real SDK interoperability test; never a production override",
    )
