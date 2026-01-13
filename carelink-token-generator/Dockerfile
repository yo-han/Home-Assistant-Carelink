ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    firefox \
    xvfb \
    dbus \
    ttf-freefont \
    font-noto \
    curl \
    && rm -rf /var/cache/apk/*

# Install geckodriver
ARG GECKODRIVER_VERSION=v0.35.0
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "x86_64" ]; then GECKO_ARCH="linux64"; \
    elif [ "$ARCH" = "aarch64" ]; then GECKO_ARCH="linux-aarch64"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi && \
    curl -sL "https://github.com/mozilla/geckodriver/releases/download/${GECKODRIVER_VERSION}/geckodriver-${GECKODRIVER_VERSION}-${GECKO_ARCH}.tar.gz" \
    -o /tmp/geckodriver.tar.gz && \
    tar -xzf /tmp/geckodriver.tar.gz -C /usr/local/bin/ && \
    rm /tmp/geckodriver.tar.gz && \
    chmod +x /usr/local/bin/geckodriver

# Create virtual environment and install Python dependencies
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir \
    flask==3.0.0 \
    requests==2.31.0 \
    pyOpenSSL==24.0.0 \
    selenium-wire==5.1.0 \
    curlify==2.2.1 \
    blinker==1.7.0

# Copy application files
COPY rootfs /

# Set working directory
WORKDIR /app

# Set display for headless Firefox
ENV DISPLAY=:99

# Expose ingress port
EXPOSE 8099

# Run script
CMD ["/run.sh"]
