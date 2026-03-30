FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false

COPY pyproject.toml ./
RUN poetry install --no-interaction --no-root 2>/dev/null || \
    pip install --no-cache-dir jinja2 psycopg2-binary python-slugify structlog boto3 pydantic

COPY . .

CMD ["python", "-m", "app.cli", "build"]
