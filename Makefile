.PHONY: logs
logs:
	journalctl -u triton.service -f

.PHONY: start
start:
	sudo systemctl start triton.service

.PHONY: stop
stop:
	sudo systemctl stop triton.service

.PHONY: restart
restart:
	sudo systemctl restart triton.service

.PHONY: status
status:
	sudo systemctl status triton.service

.PHONY: install
install:
	bash install.sh

.PHONY: update
update:
	@if [ -n "$$(git status --porcelain)" ]; then \
		git stash; \
	fi
	git pull
	@if [ -n "$$(git stash list)" ]; then \
		git stash pop; \
	fi
	$(MAKE) install

# LINTERS
# black: PEP8 code formatter
# isort: import sorting
# darglint: docstring linter
# flake8: style linter
# pylint: static analyzer
# mypy: static type checker

.PHONY: formatters
formatters:
	poetry run black run.py triton
	poetry run isort --profile black run.py triton

.PHONY: code-check
code-check:
	poetry run isort --profile black --check run.py triton
	poetry run black --check run.py triton
	poetry run darglint --verbosity 2 run.py triton
	poetry run flake8 run.py triton
	poetry run pylint run.py triton
	poetry run mypy run.py triton
