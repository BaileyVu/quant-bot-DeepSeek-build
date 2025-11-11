FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd -m trader
USER trader

COPY --chown=trader:trader pyproject.toml README.md Makefile /app/
COPY --chown=trader:trader quantbot /app/quantbot
COPY --chown=trader:trader tests /app/tests

RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --upgrade pip && \
    /app/.venv/bin/pip install -e .

ENV PATH="/app/.venv/bin:$PATH"

CMD ["python", "-m", "quantbot.live.runner", "--mode", "paper", "--exchange", "binance"]
