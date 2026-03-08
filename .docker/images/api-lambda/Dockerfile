FROM public.ecr.aws/lambda/python:3.11

# Install PostgreSQL client libs for psycopg2
RUN dnf install -y postgresql15-devel gcc python3-devel && \
    dnf clean all

# Install Python dependencies (API-only, ~300MB vs 10GB full image)
COPY requirements-api.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-api.txt

# Copy application source
COPY app/ ${LAMBDA_TASK_ROOT}/app/

# Lambda handler
CMD ["app.api.lambda_handler.handler"]
