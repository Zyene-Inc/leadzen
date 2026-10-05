# Build the company image from this checkout; see docs/docker.md.
# It runs bounded CLI jobs or the private API. Development and tests run natively.

# ── Stage 1: build a venv holding the package and its dependencies ──
FROM python:3.12.15-slim-trixie@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS deps

# The build helper is itself part of the trusted build input. Install only the
# pinned, hash-verified wheels and backend dependencies; none reaches runtime.
COPY requirements-build.lock /src/requirements-build.lock
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r /src/requirements-build.lock

COPY requirements-production.lock /src/requirements-production.lock
RUN --mount=type=cache,target=/root/.cache/uv uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install --require-hashes -r /src/requirements-production.lock
COPY . /src
RUN uv build --wheel --no-build-isolation --python /usr/local/bin/python --out-dir /wheels /src \
    && VIRTUAL_ENV=/opt/venv uv pip install --no-cache --no-deps /wheels/*.whl

# ── Stage 2: runtime ────────────────────────────────────────────
FROM python:3.12.15-slim-trixie@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d AS runtime

# One self-contained directory: the package, its dependencies, and the
# `leadzen` console script. Nothing from the build stage — no git, no uv.
COPY --from=deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

ENV EDITOR=nano

# The email-first daemon is browserless — no Playwright, no Xvfb, no VNC.
# gosu drops root → ubuntu in the entrypoint; nano backs $EDITOR.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gosu=1.17-3+b4 \
        nano=8.4-1+deb13u1 \
        libpcre2-8-0=10.46-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/*

# Runtime never installs packages; omit the base image's unused installer.
RUN /usr/local/bin/python -m pip uninstall --yes pip

# Create non-root user (slim image doesn't ship one)
RUN useradd -m -u 1000 ubuntu

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

COPY ./compose/leadzen/entrypoint /entrypoint
COPY ./compose/leadzen/start /start
RUN sed -i 's/\r$//g' /entrypoint /start && chmod +x /entrypoint /start

# The package lives in the venv, so the CRM cannot default to a path beside the
# code. Name it explicitly: /app/data is the volume operators already mount.
ENV LEADZEN_DB=/app/data/db.sqlite3
ENV LEADZEN_ENV=production

ENTRYPOINT ["/entrypoint"]
CMD ["/start"]
