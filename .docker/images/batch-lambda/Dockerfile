FROM public.ecr.aws/lambda/python:3.12

COPY requirements-batch-lambda.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-batch-lambda.txt

COPY app/ ${LAMBDA_TASK_ROOT}/app/
RUN chmod -R a+r ${LAMBDA_TASK_ROOT}/app/

# Default CMD — overridden per-Lambda in CDK
CMD ["app.llm.queue.batcher.handler"]
