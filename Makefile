# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
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
# install SLSA verifier binary, download mvnw, and gradlew.
.PHONY: setup
setup: force-upgrade setup-go setup-binaries setup-schemastore
	pre-commit install
	mkdir -p dist
	go install github.com/CycloneDX/cyclonedx-gomod/cmd/cyclonedx-gomod@v1.3.0
setup-go:
	go build -o $(PACKAGE_PATH)/bin/ $(REPO_PATH)/golang/cmd/...
setup-binaries: $(PACKAGE_PATH)/bin/slsa-verifier $(PACKAGE_PATH)/resources/mvnw $(PACKAGE_PATH)/resources/gradlew souffle gnu-sed
$(PACKAGE_PATH)/bin/slsa-verifier:
	git clone --depth 1 https://github.com/slsa-framework/slsa-verifier.git -b v2.6.0
	cd slsa-verifier/cli/slsa-verifier && go build -o $(PACKAGE_PATH)/bin/
	cd $(REPO_PATH) && rm -rf slsa-verifier
$(PACKAGE_PATH)/resources/mvnw:
	cd $(PACKAGE_PATH)/resources \
		&& wget https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper-distribution/3.1.1/maven-wrapper-distribution-3.1.1-bin.zip \
		&& unzip -o maven-wrapper-distribution-3.1.1-bin.zip \
		&& rm -r maven-wrapper-distribution-3.1.1-bin.zip \
		&& echo -e "distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.8.6/apache-maven-3.8.6-bin.zip\nwrapperUrl=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.1.1/maven-wrapper-3.1.1.jar" > .mvn/wrapper/maven-wrapper.properties \
		&& cd $(REPO_PATH)
$(PACKAGE_PATH)/resources/gradlew:
	cd $(PACKAGE_PATH)/resources \
		&& export GRADLE_VERSION=7.6 \
		&& wget https://services.gradle.org/distributions/gradle-$$GRADLE_VERSION-bin.zip \
		&& unzip -o gradle-$$GRADLE_VERSION-bin.zip \
		&& rm -r gradle-$$GRADLE_VERSION-bin.zip \
		&& gradle-$$GRADLE_VERSION/bin/gradle wrapper \
		&& cd $(REPO_PATH)
setup-schemastore: $(PACKAGE_PATH)/resources/schemastore/github-workflow.json $(PACKAGE_PATH)/resources/schemastore/LICENSE $(PACKAGE_PATH)/resources/schemastore/NOTICE
$(PACKAGE_PATH)/resources/schemastore/github-workflow.json:
	cd $(PACKAGE_PATH)/resources \
		&& mkdir -p schemastore \
		&& cd schemastore \
		&& wget https://raw.githubusercontent.com/SchemaStore/schemastore/a1689388470d1997f2e5ebd8b430e99587b8d354/src/schemas/json/github-workflow.json \
		&& cd $(REPO_PATH)
$(PACKAGE_PATH)/resources/schemastore/LICENSE:
	cd $(PACKAGE_PATH)/resources \
		&& mkdir -p schemastore \
		&& cd schemastore \
		&& wget https://raw.githubusercontent.com/SchemaStore/schemastore/a1689388470d1997f2e5ebd8b430e99587b8d354/LICENSE \
		&& cd $(REPO_PATH)
$(PACKAGE_PATH)/resources/schemastore/NOTICE:
	cd $(PACKAGE_PATH)/resources \
		&& mkdir -p schemastore \
		&& cd schemastore \
		&& wget https://raw.githubusercontent.com/SchemaStore/schemastore/a1689388470d1997f2e5ebd8b430e99587b8d354/NOTICE \
		&& cd $(REPO_PATH)

# Supports OL8+, Fedora 34+, Ubuntu 22.04+ and 24.04+, and macOS.
OS := "$(shell uname)"
ifeq ($(OS), "Darwin")
  OS_DISTRO := "Darwin"
else
  ifeq ($(OS), "Linux")
    OS_DISTRO := "$(shell grep '^NAME=' /etc/os-release | sed 's/^NAME=//' | sed 's/"//g')"
    OS_MAJOR_VERSION := "$(shell grep '^VERSION=' /etc/os-release | sed -r 's/^[^0-9]+([0-9]+)\..*/\1/')"
  endif
endif
# If Souffle cannot be installed, we advise the user to install it manually
# and return status code 0, which is not considered a failure.
.PHONY: souffle
souffle:
	if ! command -v souffle; then \
	  echo "Installing system dependency: souffle" && \
	  case $(OS_DISTRO) in \
	    "Oracle Linux") \
	      sudo dnf -y install https://github.com/souffle-lang/souffle/releases/download/2.5/x86_64-oraclelinux-9-souffle-2.5-Linux.rpm;; \
	    "Fedora Linux") \
	      sudo dnf -y install https://github.com/souffle-lang/souffle/releases/download/2.5/x86_64-fedora-41-souffle-2.5-Linux.rpm;; \
	    "Ubuntu") \
	      if [ $(OS_MAJOR_VERSION) == "24" ]; then \
	        wget https://github.com/souffle-lang/souffle/releases/download/2.5/x86_64-ubuntu-2404-souffle-2.5-Linux.deb -O ./souffle.deb; \
	      elif [ $(OS_MAJOR_VERSION) == "22" ]; then \
	        wget https://github.com/souffle-lang/souffle/releases/download/2.5/x86_64-ubuntu-2204-souffle-2.5-Linux.deb -O ./souffle.deb; \
	      else \
	        echo "Unsupported Ubuntu major version: $(OS_MAJOR_VERSION)"; exit 0; \
	      fi; \
	      sudo apt install ./souffle.deb; \
	      rm ./souffle.deb;; \
	    "Darwin") \
	      if command -v brew; then \
	        brew install --HEAD souffle-lang/souffle/souffle; \
	      else \
	        echo "Unable to install Souffle. Please install it manually." && exit 0; \
	      fi;; \
	    *) \
	      echo "Unsupported OS distribution: $(OS_DISTRO)"; exit 0;; \
	  esac; \
	fi && \
	command -v souffle

# Install gnu-sed on mac using homebrew
.PHONY: gnu-sed
gnu-sed:
	if [ "$(OS_DISTRO)" == "Darwin" ]; then \
	  if ! command -v gsed; then \
	    if command -v brew; then \
	      brew install gnu-sed; \
	    elif command -v port; then \
	      sudo port install gsed; \
	    else \
	      echo "Unable to install GNU sed on macOS. Please install it manually." && exit 1; \
	    fi; \
	  fi; \
	fi;

# Install or upgrade an existing virtual environment based on the
# package dependencies declared in pyproject.toml.
# Go dependencies are only upgraded by Dependabot and managed differently
# from Python dependencies and by default the upgrade target does not
# upgrade Go dependencies. To upgrade the Go dependencies use the
# `upgrade-go` target directly, which uses the code snippet suggested
# here instead of `go get -u` to avoid updating indirect dependencies
# and creating a broken state:
# https://github.com/golang/go/issues/28424#issuecomment-1101896499
.PHONY: upgrade force-upgrade
upgrade: .venv/upgraded-on
.venv/upgraded-on: pyproject.toml
	python -m pip install --upgrade pip
	python -m pip install --upgrade wheel
	python -m pip install --upgrade --upgrade-strategy eager --editable .[actions,dev,docs,hooks,test,test-docker]
	$(MAKE) upgrade-quiet
force-upgrade:
	rm -f .venv/upgraded-on
	$(MAKE) upgrade
upgrade-quiet:
	echo "Automatically generated by Python Package Makefile on $$(date '+%Y-%m-%d %H:%M:%S %z')." > .venv/upgraded-on
upgrade-go:
	go get $$(go list -f '{{if not (or .Main .Indirect)}}{{.Path}}{{end}}' -m all)
	go mod tidy

# Install dependencies for GitHub Actions, such as commitizen that we need as part of
# the automatic release in the release GitHub Actions and with this target we can skip
# setting up unrelated packages.
.PHONY: setup-github-actions
setup-github-actions:
	python -m pip install --upgrade pip
	python -m pip install --upgrade wheel
	python -m pip install --upgrade --upgrade-strategy eager .[actions]

# Install dependencies for the integration test utility script in workflow to
# test the docker image.
.PHONY: setup-integration-test-utility-for-docker
setup-integration-test-utility-for-docker:
	python -m pip install --upgrade pip
	python -m pip install --upgrade wheel
	python -m pip install --upgrade --upgrade-strategy eager .[test-docker]

# Generate a Software Bill of Materials (SBOM).
.PHONY: sbom
sbom: requirements
	cyclonedx-py requirements --output-format json --outfile dist/$(PACKAGE_NAME)-$(PACKAGE_VERSION)-sbom.json
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
.PHONY: check check-code check-bandit check-flake8 check-lint check-mypy check-go check-actionlint
check-code: check-bandit check-flake8 check-lint check-mypy check-go check-actionlint
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
check-actionlint:
	pre-commit run actionlint --all-files
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
# Note: to disable npm tests set `NO_NPM` environment variable to `TRUE`.
.PHONY: integration-test
integration-test:
	if [ "${NO_NPM}" == "TRUE" ]; then \
    	echo "Note: NO_NPM environment variable is set to TRUE, so npm tests will be skipped."; \
		python ./tests/integration/run.py \
			run \
			--include-tag macaron-python-package \
			--exclude-tag skip \
			--exclude-tag npm-registry-testcase \
			./tests/integration/cases/...; \
	else \
		python ./tests/integration/run.py \
			run \
			--include-tag macaron-python-package \
			--exclude-tag skip \
			./tests/integration/cases/...; \
	fi

.PHONY: integration-test-docker
integration-test-docker:
	python ./tests/integration/run.py \
		run \
		--macaron scripts/release_scripts/run_macaron.sh \
		--include-tag macaron-docker-image \
		--exclude-tag skip \
		./tests/integration/cases/...

# Update the expected results of the integration tests after generating the actual results.
.PHONY: integration-test-update
integration-test-update:
	python ./tests/integration/run.py \
		update \
		--exclude-tag skip \
		./tests/integration/cases/...

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
docs: docs-clean
	$(MAKE) -C docs/ html

# Generate API reference pages in the documentation using `sphinx-apidoc`.
.PHONY: docs-api
docs-api:
	sphinx-apidoc --no-toc --module-first --force --maxdepth 1 --output-dir docs/source/pages/developers_guide/apidoc/ src/

# Combine the two targets `docs-api` and `docs`:
# First generate API reference pages, then build the HTML documentation.
.PHONY: docs-full
docs-full: docs-api docs

# Build the Docker image. The image name and tag are read from IMAGE_NAME and RELEASE_TAG
# environment variables, respectively. By default "test" is used as the image tag.
.PHONY: build-docker
build-docker:
	if [ -z "${IMAGE_NAME}" ]; then \
	  echo "Please set IMAGE_NAME environment variable!" && exit 1; \
	fi
	scripts/dev_scripts/build_docker.sh "${IMAGE_NAME}" $(REPO_PATH) "${RELEASE_TAG}"

# Push the Docker image. The image name and tag are read from IMAGE_NAME and RELEASE_TAG
# environment variables, respectively.
.PHONY: push-docker
push-docker:
	if [ -z "${IMAGE_NAME}" ] || [ -z "${RELEASE_TAG}" ]; then \
	  echo "Please set IMAGE_NAME and RELEASE_TAG environment variables!" && exit 1; \
	fi
	docker push "${IMAGE_NAME}":latest
	docker push "${IMAGE_NAME}":"${RELEASE_TAG}"

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
.PHONY: dist-clean bin-clean docs-clean clean
dist-clean:
	rm -fr dist/*
	rm -f requirements.txt
bin-clean:
	rm -fr $(PACKAGE_PATH)/bin/*
docs-clean:
	rm -fr docs/_build/
clean: dist-clean bin-clean docs-clean
	rm -fr .coverage .hypothesis/ .mypy_cache/ .pytest_cache/

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
