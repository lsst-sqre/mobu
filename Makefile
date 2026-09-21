.PHONY: help
help:
	@echo "Make targets for mobu"
	@echo "make init - Set up dev environment"
	@echo "make linkcheck - Check for broken links in documentation"
	@echo "make run - Run development instance of server"
	@echo "make update - Update pinned dependencies and run make init"
	@echo "make update-deps - Update pinned dependencies"

.PHONY: init
init:
	uv sync --frozen --all-groups
	uv run prek install

.PHONY: run
run:
	uv run nox -s run

.PHONY: update
update: update-deps init

.PHONY: update-deps
update-deps:
	uv lock --upgrade
	uv run --only-group=lint prek autoupdate
	./scripts/update-uv-version.sh
