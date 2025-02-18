.PHONY: help
help:
	@echo "Make targets for mobu"
	@echo "make init - Set up dev environment"
	@echo "make run - Run development instance of server"
	@echo "make update - Update pinned dependencies and run make init"
	@echo "make update-deps - Update pinned dependencies"

.PHONY: init
init:
	pip install --upgrade uv
	uv pip install pre-commit tox
	uv pip install --editable .
	uv pip install -r requirements/main.txt -r requirements/dev.txt
	rm -rf .tox
	pre-commit install

.PHONY: run
run:
	tox run -e run

.PHONY: update
update: update-deps init

.PHONY: update-deps
update-deps:
	pip install --upgrade uv
	uv pip install pre-commit
	pre-commit autoupdate
	uv pip compile --upgrade --universal --generate-hashes		\
	    --output-file requirements/main.txt pyproject.toml
	uv pip compile --upgrade --universal --generate-hashes		\
	    --output-file requirements/dev.txt requirements/dev.in
	uv pip compile --upgrade --universal --generate-hashes		\
	    --output-file requirements/tox.txt requirements/tox.in
