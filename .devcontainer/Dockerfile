FROM mcr.microsoft.com/devcontainers/python:3.12

# Install GitHub CLI
RUN rm -f /etc/apt/sources.list.d/yarn*.list || true && \
    rm -f /etc/apt/trusted.gpg.d/yarn*.gpg || true && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    apt-get install -y gh && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Railway CLI
RUN curl -fsSL https://railway.app/install.sh | sh

# Configure Git
RUN git config --global pull.ff true

# Install Poetry
RUN pip install poetry && \
    poetry config virtualenvs.in-project true && \
    poetry config virtualenvs.create true

# Install poetry-shell plugin
RUN poetry self add poetry-plugin-shell
