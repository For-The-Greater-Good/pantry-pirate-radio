# Dockerfile for CDK infrastructure deployment and testing
FROM python:3.11-slim

# Install Node.js for CDK CLI
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CDK CLI
RUN npm install -g aws-cdk

# Set working directory
WORKDIR /infra

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy infrastructure code
COPY . .

# Default command: synthesize templates
CMD ["cdk", "synth"]
