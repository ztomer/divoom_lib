# Contributing to Divoom Control

First off, thank you for considering contributing to Divoom Control! It's people like you that make open source software such a great community.

## Where to Start

There are many ways to contribute, from writing tutorials or blog posts, improving the documentation, submitting bug reports and feature requests or writing code which can be incorporated into Divoom Control itself.

## Submitting a Bug Report

If you find a bug, please open an issue on our GitHub repository. Please include as much information as possible, including:

*   A clear and descriptive title.
*   A detailed description of the bug, including steps to reproduce it.
*   The version of Divoom Control you are using.
*   Your Python version.
*   Your operating system.

## Submitting a Feature Request

If you have an idea for a new feature, please open an issue on our GitHub repository. Please include:

*   A clear and descriptive title.
*   A detailed description of the feature, including why you think it would be useful.

## Contributing Code

If you would like to contribute code to Divoom Control, please follow these steps:

1.  Fork the repository on GitHub.
2.  Create a new branch for your feature or bug fix.
3.  Write your code, including tests to cover your changes.
4.  Ensure that your code follows the project's coding style.
5.  Submit a pull request to the `main` branch of the Divoom Control repository.

### Setting up a Development Environment

To set up a development environment, you will need to have Python 3.8 or later installed. You can then install the project's dependencies using pip:

```bash
pip install -r requirements.txt
```

### Running the Tests

To run the tests, you can use pytest:

```bash
pytest
```

## Code of Conduct

Please note that this project is released with a Contributor Code of Conduct. By participating in this project you agree to abide by its terms.

## For AI Agents (and Curious Humans)

If you are an AI agent working on this codebase, or a human looking for a quick start:

1.  **Read `ARCHITECTURE.md`**: This file contains a high-level overview of the system, protocol details, and common pitfalls. It is designed to give you context quickly.
2.  **Use `scripts/mock_device.py`**: This script provides a `MockBleakClient` that simulates a Divoom device. You can use it to verify protocol logic without needing physical hardware.
