# Canary Swarm sandbox runner.
# Untrusted worker: drives Chromium via Playwright, holds ZERO secrets.
# Started only by the control plane with the BUILD_SPEC Section 3 flags.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Read-only rootfs: everything writable lives on the /tmp tmpfs.
ENV HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    XDG_CONFIG_HOME=/tmp/.config \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The base image ships browsers in /ms-playwright but not the Python package.
RUN pip install --no-cache-dir playwright==1.49.0

WORKDIR /app
COPY runner.py /app/runner.py

USER pwuser
ENTRYPOINT ["python", "/app/runner.py"]
