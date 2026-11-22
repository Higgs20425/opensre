# OpenSRE runner for the Jenkins lab, kept off the host. Built by compose.yaml
# with the repository root as context, so it runs this checkout's code.
#
# The image holds no credentials: the root .dockerignore keeps .env out of the
# build context, and model sign-in and integration setup happen inside the
# running container and are removed with it.
FROM python:3.13-bookworm

# Set to false to skip the Claude Code CLI when another model provider is used.
ARG INSTALL_CLAUDE_CODE=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --disable-pip-version-check uv \
    && useradd --uid 1000 --create-home --shell /bin/bash opensre

USER opensre
WORKDIR /home/opensre/opensre

ENV PATH="/home/opensre/opensre/.venv/bin:/home/opensre/.local/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    UV_PYTHON_DOWNLOADS=never \
    OPENSRE_NO_TELEMETRY=1 \
    DO_NOT_TRACK=1

# Dependencies first, so editing source does not reinstall them.
COPY --chown=opensre:opensre pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-cache

COPY --chown=opensre:opensre . .
RUN uv sync --frozen --no-cache

RUN if [ "${INSTALL_CLAUDE_CODE}" = "true" ]; then \
        curl -fsSL https://claude.ai/install.sh | bash; \
    fi

CMD ["sleep", "infinity"]
