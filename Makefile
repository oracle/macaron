# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# Use bash as the shell when executing a rule's recipe. For more details:
# https://www.gnu.org/software/make/manual/html_node/Choosing-the-Shell.html
SHELL := bash

# Set the package's name, version, and path for use throughout the Makefile.
PACKAGE_NAME := macaron
PACKAGE_VERSION := $(shell python -c $$'try: import $(PACKAGE_NAME); print($(PACKAGE_NAME).__version__);\nexcept: print("unknown");')
PACKAGE_PATH := $(shell pwd)/src/$(PACKAGE_NAME)
REPO_PATH := $(shell pwd)
PYTHON ?= python3.11

# This variable contains the first goal that matches any of the listed goals
# here, else it contains an empty string. The net effect is to filter out
# whether this current run of `make` requires a Python virtual environment
# by checking if any of the given goals requires a virtual environment (all
# except the 'venv' and the various 'clean' and 'nuke' goals do). Note that
# checking for 'upgrade' and 'check' goals includes all of their variations.
NEED_VENV := $(or \
  $(findstring all,$(MAKECMDGOALS)), \
  $(findstring setup,$(MAKECMDGOALS)), \
  $(findstring upgrade,$(MAKECMDGOALS)), \
  $(findstring sbom,$(MAKECMDGOALS)), \
  $(findstring requirements,$(MAKECMDGOALS)), \
  $(findstring audit,$(MAKECMDGOALS)), \
  $(findstring check,$(MAKECMDGOALS)), \
  $(findstring test,$(MAKECMDGOALS)), \
  $(findstring test-integration,$(MAKECMDGOALS)), \
  $(findstring dist,$(MAKECMDGOALS)), \
  $(findstring docs,$(MAKECMDGOALS)), \
  $(findstring prune,$(MAKECMDGOALS)), \
)
ifeq ($(NEED_VENV),)
  # None of the current goals requires a virtual environment.
else
  ifeq ($(origin VIRTUAL_ENV),undefined)
    $(warning No Python virtual environment found, proceeding anyway)
  else
    ifeq ($(wildcard .venv/upgraded-on),)
      $(warning Python virtual environment not yet set up, proceeding anyway)
    endif
  endif
endif

# If the project configuration file has been updated (package deps or
# otherwise) then warn the user and suggest resolving the conflict.
ifeq ($(shell test pyproject.toml -nt .venv/upgraded-on; echo $$?),0)
  $(warning pyproject.toml was updated, consider `make upgrade` if your packages have changed)
  $(warning If this is not correct then run `make upgrade-quiet`)
endif

# The SOURCE_DATE_EPOCH environment variable allows the `flit` tool to
# reproducibly build packages: https://flit.pypa.io/en/latest/reproducible.html
# If that variable doesn't exist, then set it here to the current epoch.
ifeq ($(origin SOURCE_DATE_EPOCH),undefined)
  SOURCE_DATE_EPOCH := $(shell date +%s)
endif

# Check, test, and build artifacts for this package.
.PHONY: all
all: check test dist docs

# Create a virtual environment, either for Python or using
# the Python interpreter specified in the PYTHON environment variable. Also
# create an empty pip.conf file to ensure that `pip config` modifies this
# venv only, unless told otherwise.
.PHONY: venv
venv:
	if [ ! -z "${VIRTUAL_ENV}" ]; then \
	  echo "Found an activated Python virtual environment, exiting" && exit 1; \
	fi
	if [ -d .venv/ ]; then \
	  echo "Found an inactive Python virtual environment, please activate or nuke it" && exit 1; \
	fi
	echo "Creating virtual environment in .venv/ for ${PYTHON}"; \
	${PYTHON} -m venv --upgrade-deps --prompt . .venv; \
	touch .venv/pip.conf

# Set up a newly created virtual environment. Note: pre-commit uses the
# venv's Python interpreter, so if you've created multiple venvs then
# pre-commit's git hooks run against the most recently set up venv.
# The _build.yaml GitHub Actions workflow expects dist directory to exist.
# So we create the dist dir if it doesn't exist in the setup target.
# See https://packaging.python.org/en/latest/tutorials/packaging-projects/#generating-distribution-archives.
# We also install cyclonedx-go to generate SBOM for Go, compile the Go modules,
# install SLSA verifier binary, and download mvnw.
.PHONY: setup
setup: force-upgrade setup-go setup-binaries
	pre-commit install
	mkdir -p dist
	go install github.com/CycloneDX/cyclonedx-gomod/cmd/cyclonedx-gomod@v1.3.0
setup-go:
	go build -o $(PACKAGE_PATH)/bin/ $(REPO_PATH)/golang/cmd/...
setup-binaries: $(PACKAGE_PATH)/bin/slsa-verifier $(PACKAGE_PATH)/resources/mvnw
$(PACKAGE_PATH)/bin/slsa-verifier:
	git clone --depth 1 https://github.com/slsa-framework/slsa-verifier.git -b v2.0.1
	cd slsa-verifier/cli/slsa-verifier && go build -o $(PACKAGE_PATH)/bin/
	cd $(REPO_PATH) && rm -rf slsa-verifier
$(PACKAGE_PATH)/resources/mvnw:
	cd $(PACKAGE_PATH)/resources \
		&& wget https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper-distribution/3.1.1/maven-wrapper-distribution-3.1.1-bin.zip \
		&& unzip -o maven-wrapper-distribution-3.1.1-bin.zip \
		&& rm -r maven-wrapper-distribution-3.1.1-bin.zip \
		&& echo -e "distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.8.6/apache-maven-3.8.6-bin.zip\nwrapperUrl=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.1.1/maven-wrapper-3.1.1.jar" > .mvn/wrapper/maven-wrapper.properties \
		&& cd $(REPO_PATH)

# Install or upgrade an existing virtual environment based on the
# package dependencies declared in pyproject.toml and go.mod.
.PHONY: upgrade force-upgrade upgrade-go
upgrade: .venv/upgraded-on upgrade-go
.venv/upgraded-on: pyproject.toml
	python -m pip install --upgrade pip
	python -m pip install --upgrade wheel
	python -m pip install --upgrade --upgrade-strategy eager --editable .[actions,dev,docs,hooks,test]
	$(MAKE) upgrade-quiet
force-upgrade: upgrade-go
	rm -f .venv/upgraded-on
	$(MAKE) upgrade
upgrade-quiet:
	echo "Automatically generated by Python Package Makefile on $$(date '+%Y-%m-%d %H:%M:%S %z')." > .venv/upgraded-on
upgrade-go:
	go get -u ./...
	go mod tidy

# Generate a Software Bill of Materials (SBOM).
.PHONY: sbom
sbom: requirements
	cyclonedx-bom --force --requirements --format json --output dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-sbom.json
	$$HOME/go/bin/cyclonedx-gomod mod -json -output dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-sbom-go.json $(REPO_PATH)

# Generate a requirements.txt file containing version and integrity hashes for all
# packages currently installed in the virtual environment. There's no easy way to
# do this, see also: https://github.com/pypa/pip/issues/4732
#
# If using a private package index, make sure that it implements the JSON API:
# https://warehouse.pypa.io/api-reference/json.html
#
# We also want to make sure that this package itself is added to the requirements.txt
# file, and if possible even with proper hashes.
.PHONY: requirements
requirements: requirements.txt
requirements.txt: pyproject.toml
	echo -n "" > requirements.txt
	for pkg in $$(python -m pip freeze --local --disable-pip-version-check --exclude-editable); do \
	  pkg=$${pkg//[$$'\r\n']}; \
	  echo -n $$pkg >> requirements.txt; \
	  echo "Fetching package metadata for requirement '$$pkg'"; \
	  [[ $$pkg =~ (.*)==(.*) ]] && curl -s https://pypi.org/pypi/$${BASH_REMATCH[1]}/$${BASH_REMATCH[2]}/json | python -c "import json, sys; print(''.join(f''' \\\\\n    --hash=sha256:{pkg['digests']['sha256']}''' for pkg in json.load(sys.stdin)['urls']));" >> requirements.txt; \
	done
	echo -e -n "$(PACKAGE_NAME)==$(PACKAGE_VERSION)" >> requirements.txt
	if [ -f dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION).tar.gz ]; then \
	  echo -e -n " \\\\\n    $$(python -m pip hash --algorithm sha256 dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION).tar.gz | grep '^\-\-hash')" >> requirements.txt; \
	fi
	if [ -f dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-py3-none-any.whl ]; then \
	  echo -e -n " \\\\\n    $$(python -m pip hash --algorithm sha256 dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-py3-none-any.whl | grep '^\-\-hash')" >> requirements.txt; \
	fi
	echo "" >> requirements.txt
	cp requirements.txt dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-requirements.txt

# Audit the currently installed packages. Skip packages that are installed in
# editable mode (like the one in development here) because they may not have
# a PyPI entry; also print out CVE description and potential fixes if audit
# found an issue.
.PHONY: audit
audit:
	if ! $$(python -c "import pip_audit" &> /dev/null); then \
	  echo "No package pip_audit installed, upgrade your environment!" && exit 1; \
	fi;
	python -m pip_audit --skip-editable --desc on --fix --dry-run

# Run some or all checks over the package code base.
.PHONY: check check-code check-bandit check-flake8 check-lint check-mypy check-go
check-code: check-bandit check-flake8 check-lint check-mypy check-go
check-bandit:
	pre-commit run bandit --all-files
check-flake8:
	pre-commit run flake8 --all-files
check-lint:
	pre-commit run pylint --all-files
check-mypy:
	pre-commit run mypy --all-files
check-go:
	pre-commit run golangci-lint --all-files
	pre-commit run go-build-mod --all-files
	pre-commit run go-build-repo-mod --all-files
	pre-commit run go-mod-tidy --all-files
	pre-commit run go-mod-tidy-repo --all-files
	pre-commit run go-test-mod --all-files
	pre-commit run go-test-repo-mod --all-files
	pre-commit run go-vet-mod --all-files
	pre-commit run go-vet-repo-mod --all-files
	pre-commit run go-fmt --all-files
	pre-commit run go-fmt-repo --all-files
check:
	pre-commit run --all-files


# Run all unit tests. The --files option avoids stashing but passes files; however,
# the hook setup itself does not pass files to pytest (see .pre-commit-config.yaml).
.PHONY: test
test: test-go
	pre-commit run pytest --hook-stage push --files tests/
test-go:
	go test ./golang/...

# Run the integration tests.
.PHONY: integration-test
integration-test:
	scripts/dev_scripts/integration_tests.sh $(REPO_PATH) $$HOME

# Build a source distribution package and a binary wheel distribution artifact.
# When building these artifacts, we need the environment variable SOURCE_DATE_EPOCH
# set to the build date/epoch. For more details, see: https://flit.pypa.io/en/latest/reproducible.html
.PHONY: dist
dist: dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-py3-none-any.whl dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION).tar.gz dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-docs-html.zip dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-build-epoch.txt
dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-py3-none-any.whl: check test integration-test
	flit build --setup-py --format wheel
dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION).tar.gz: check test integration-test
	flit build --setup-py --format sdist
dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-docs-html.zip: docs
	python -m zipfile -c dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-docs-html.zip docs/_build/html
dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-build-epoch.txt:
	echo $(SOURCE_DATE_EPOCH) > dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-build-epoch.txt

# Build the HTML documentation from the package's source.
.PHONY: docs
docs: docs/_build/html/index.html
docs/_build/html/index.html:
	$(MAKE) -C docs/ html

# Prune the packages currently installed in the virtual environment down to the required
# packages only. Pruning works in a roundabout way, where we first generate the wheels for
# all installed packages into the build/wheelhouse/ folder. Next we wipe all packages and
# then reinstall them from the wheels while disabling the PyPI index server. Thus we ensure
# that the same package versions are reinstalled. Use with care!
.PHONY: prune
prune:
	mkdir -p build/
	python -m pip freeze --local --disable-pip-version-check --exclude-editable > build/prune-requirements.txt
	python -m pip wheel --wheel-dir build/wheelhouse/ --requirement build/prune-requirements.txt
	python -m pip wheel --wheel-dir build/wheelhouse/ .
	python -m pip uninstall --yes --requirement build/prune-requirements.txt
	python -m pip install --no-index --find-links=build/wheelhouse/ --editable .
	rm -fr build/

# Clean test caches and remove build artifacts.
.PHONY: dist-clean bin-clean clean
dist-clean:
	rm -fr dist/*
	rm -f requirements.txt
bin-clean:
	rm -fr bin/*
clean: dist-clean bin-clean
	rm -fr .coverage .hypothesis/ .mypy_cache/ .pytest_cache/
	rm -fr docs/_build/

# Remove code caches, or the entire virtual environment if it is deactivated..
.PHONY: nuke-caches nuke
nuke-caches: clean
	find src/ -type d -name __pycache__ -exec rm -fr {} +
	find tests/ -type d -name __pycache__ -exec rm -fr {} +
nuke-mvnw:
	cd $(PACKAGE_PATH)/resources \
	&& rm mvnw mvnw.cmd mvnwDebug mvnwDebug.cmd \
	&& cd $(REPO_PATH)
nuke: nuke-caches nuke-mvnw
	if [ ! -z "${VIRTUAL_ENV}" ]; then \
	  echo "Please deactivate the virtual environment first!" && exit 1; \
	fi
	rm -fr .venv/
