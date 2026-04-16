# Contributing to KatalogAI

Thank you for your interest in contributing to KatalogAI!

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it before contributing.

## How to Contribute

### Reporting Bugs

1. **Search existing issues** - Check if the bug has already been reported
2. **Create a detailed issue** - Use the bug report template
3. **Include reproduction steps** - Help us understand the issue

### Suggesting Features

1. **Search existing discussions** - Check if the feature has been discussed
2. **Create a feature request** - Use the feature request template
3. **Explain the use case** - Help us understand why this feature is needed

### Pull Requests

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/my-feature`
3. **Make your changes** - Follow our coding standards
4. **Run tests**: `make test`
5. **Run linting**: `make lint`
6. **Run type checking**: `make typecheck`
7. **Commit with clear messages**: [Conventional Commits](https://www.conventionalcommits.org/)
8. **Push to your fork**
9. **Submit a pull request**

## Development Setup

```bash
# Clone and setup
git clone https://github.com/katalogai/katalogai.git
cd katalogai
pip install -e ".[dev]"

# Run tests
make test
```

## Coding Standards

- **Format**: Use `ruff` for formatting
- **Type Checking**: Use `mypy` with strict mode
- **Testing**: Write tests for new features; aim for >80% coverage
- **Docstrings**: Use Google-style docstrings

## Commit Message Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Example:
```
feat(ingest): add support for batch text ingestion

- Added batch endpoint for processing multiple products
- Updated confidence scoring for batch items
```

## Review Process

- PRs require at least one approval
- All CI checks must pass
- Address review feedback promptly

## Questions?

- Open an issue for bugs/feature requests
- Start a discussion for general questions

Thank you for contributing!