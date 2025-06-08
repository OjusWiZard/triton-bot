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
	black run.py triton
	isort run.py triton

.PHONY: code-check
code-check:
	black --check run.py triton
	isort --profile black --check run.py triton
	darglint --verbosity 2 run.py triton
	flake8 run.py triton
	pylint run.py triton
	mypy run.py triton
