.PHONY: install dev test clean

install:
	@command -v pipx >/dev/null 2>&1 || { \
		echo "pipx not found — install it first: https://pipx.pypa.io/"; exit 1; }
	pipx install -e . --force
	@echo
	@echo "Installed. Run: irclaude setup"

dev:
	pip install -e ".[dev]"

test:
	pytest -q

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
