ARG BUILD_FROM=ghcr.io/home-assistant/base-python:3.13-alpine3.23
FROM $BUILD_FROM

# Install system build dependencies
# g++ is needed by some Python packages (matplotlib, scipy) when building from source
RUN apk add --no-cache \
    curl \
    bash \
    gcc \
    g++ \
    musl-dev \
    python3-dev \
    libffi-dev \
    && rm -rf /var/cache/apk/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Set the working directory
WORKDIR /app

# Copy dependency files first (for Docker layer caching)
COPY pyproject.toml uv.lock ./

# Install Python dependencies using uv (frozen = exact versions from uv.lock)
# --no-build-isolation ensures we use pre-built wheels where available
RUN uv sync --frozen --no-dev

# Copy the application source code
COPY heatmap ./heatmap
COPY scripts ./scripts
COPY main.py ./main.py

# Copy the add-on startup script
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
