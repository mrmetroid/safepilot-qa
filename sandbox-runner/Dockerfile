# SafePilot QA sandbox runner. Untrusted worker: holds zero secrets.
#
# BUILD_SPEC Section 2.2 names mcr.microsoft.com/playwright:v1.49.0-jammy and allows
# another official jammy Playwright image. We use the official Python variant so the
# runner can stay in Python. Browsers in this image match playwright==1.49.0.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy@sha256:70c06141ac9041eedef4a68387ea978ceb090c37bd5b66583353b7fe17b9f3d7

# The root filesystem is read-only at runtime; /tmp is the only writable path (tmpfs).
# Chromium writes profile and crash data under $HOME, so point it at /tmp.
ENV HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY runner.py /app/runner.py

USER pwuser

# "-" reads the job as the first JSON line on stdin, then one action per line.
CMD ["python", "/app/runner.py", "-"]
