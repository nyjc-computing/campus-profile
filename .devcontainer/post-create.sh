#!/bin/bash

# Configure Git to use fast-forward pulls
git config pull.ff true

# Install Poetry
pip install poetry

# Configure Poetry to use in-project virtualenv
poetry config virtualenvs.in-project true
poetry config virtualenvs.create true

# Install project dependencies
poetry install --no-root

# Install poetry-shell plugin
poetry self add poetry-plugin-shell
