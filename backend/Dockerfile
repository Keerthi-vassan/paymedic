# Playwright's own image, not python:3.12-slim -- Playwright's `--with-deps`
# OS package installer doesn't yet know Debian trixie (python:3.12-slim's
# base as of this writing), and fails on renamed font packages there. This
# image ships Python 3.12 + Chromium + every OS-level dependency already
# verified compatible by Playwright itself, so `playwright install chromium`
# below only needs to fetch the browser binary, not fight apt.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Chromium only -- the real-execution automation (app/services/execution/)
# never touches Firefox/WebKit, no need to ship them.
RUN playwright install chromium

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
