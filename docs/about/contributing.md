# Contributing

Contributions are welcome! We are excited to see the community help improve and grow DuoORM.

## Getting Started

If you're interested in contributing, here's how you can get started:

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** to your local machine.
3.  **Set up a virtual environment** and install the development dependencies:
    ```bash
    # Create and activate a virtual environment
    python -m venv .venv
    source .venv/bin/activate

    # Install the package in editable mode with development extras
    pip install -e ".[dev]"
    ```
4.  **Make your changes**. Please add tests for any new features or bug fixes.
5.  **Run the test suite** to ensure everything is working correctly.
    ```bash
    # Example for SQLite
    pytest --db-url "sqlite:///./test.db"
    ```
6.  **Submit a pull request** with a clear description of your changes.

## Areas for Contribution

We are looking for help in several areas:

-   **Bug Fixes**: If you find a bug, please open an issue first, and then feel free to submit a pull request with a fix.
-   **New Features**: If you have an idea for a new feature, please open an issue to discuss it.
-   **Documentation**: Improvements to the documentation are always welcome.
-   **Dialect Support**: Expanding and improving support for different database backends (MySQL, Oracle, MSSQL) is a high priority.

Thank you for your interest in contributing to DuoORM!
