FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/yo-han/Home-Assistant-Carelink"
LABEL org.opencontainers.image.description="Carelink Token Tool - obtain login tokens for Home Assistant Carelink integration"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    firefox-esr \
    wget \
    curl \
    gnupg \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    supervisor \
    procps \
    autocutsel \
    xclip \
    && rm -rf /var/lib/apt/lists/*

# Install geckodriver - detect architecture
ARG GECKODRIVER_VERSION=v0.35.0
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then GECKO_ARCH="linux64"; \
    elif [ "$ARCH" = "arm64" ]; then GECKO_ARCH="linux-aarch64"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi && \
    echo "Installing geckodriver ${GECKODRIVER_VERSION} for ${GECKO_ARCH}" && \
    wget -q "https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-${GECKO_ARCH}.tar.gz" -O /tmp/geckodriver.tar.gz && \
    tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin/ && \
    rm /tmp/geckodriver.tar.gz && \
    chmod +x /usr/local/bin/geckodriver && \
    geckodriver --version

# Install Python dependencies (pinned versions for reproducibility)
RUN pip install --no-cache-dir \
    requests==2.31.0 \
    pyOpenSSL==24.0.0 \
    selenium-wire==5.1.0 \
    curlify==2.2.1 \
    blinker==1.7.0

# Create app directory
WORKDIR /app

# Copy the login script
COPY carelink_login.py /app/
COPY start.sh /app/
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create output directory
RUN mkdir -p /output

# Set permissions
RUN chmod +x /app/start.sh

# Expose noVNC port and file server port
EXPOSE 6080 8000

# Set display
ENV DISPLAY=:99

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:6080/ || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
