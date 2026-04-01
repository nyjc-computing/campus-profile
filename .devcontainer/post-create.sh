#!/bin/bash

# Configure Git to use fast-forward pulls only
git config pull.ff true

# Install Poetry
pip install poetry

# Configure Poetry to use in-project virtualenv
poetry config virtualenvs.in-project true
poetry config virtualenvs.create true

# Install poetry-shell plugin
poetry self add poetry-plugin-shell

# Install GitHub CLI
# Remove any problematic third-party apt sources (e.g., yarn) that may have broken GPG keys
rm -f /etc/apt/sources.list.d/yarn*.list || true
rm -f /etc/apt/trusted.gpg.d/yarn*.gpg || true

# Import GitHub CLI GPG key and add repository
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list
apt-get update
apt-get install -y gh

# Install project dependencies
poetry install --no-root
