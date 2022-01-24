BLACK=black
MYPY=mypy
PYLINT=pylint
PYTHON=python3

# Run a Python tool with a specified module name
pytool = . venv/bin/activate && $(PYTHON) -m $(1) $(2)

.PHONY: all beautiful check clean format lint pip-compile pip-sync test type-check venv

clean:
	rm -rf venv build dist *.egg-info
	find . -iname "*.pyc" -exec rm -- {} +

venv: venv/bin/activate
	. venv/bin/activate

venv/bin/activate:
	test -d venv || $(PYTHON) -m venv venv
	$(call pytool, pip, install pip-tools)

pip-compile: venv
	. venv/bin/activate && $(MAKE) -C requirements all

pip-sync: venv pip-compile
	. venv/bin/activate && venv/bin/pip-sync $(wildcard requirements/*.txt)

docker-setup: venv pip-sync

check: type-check test lint

format: venv
	$(call pytool, $(BLACK), *.py)

beautiful: format

lint: venv
	$(call pytool, $(PYLINT), *.py)

type-check: venv
	$(call pytool, $(MYPY), --check-untyped-defs *.py )

test: venv
	$(call pytool, unittest, discover -s test)

