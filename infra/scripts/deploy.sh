#!/bin/bash
# Deploy Pantry Pirate Radio infrastructure to AWS
#
# Usage:
#   ./scripts/deploy.sh [environment] [options]
#
# Arguments:
#   environment    Target environment: dev, staging, prod (default: dev)
#
# Options:
#   --diff         Show diff instead of deploying
#   --synth        Only synthesize templates
#   --destroy      Destroy all stacks (with confirmation)
#   --help         Show this help message

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"

# Default values
ENVIRONMENT="${1:-dev}"
ACTION="deploy"

# Parse options
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --diff)
            ACTION="diff"
            ;;
        --synth)
            ACTION="synth"
            ;;
        --destroy)
            ACTION="destroy"
            ;;
        --help|-h)
            head -20 "$0" | tail -n +2 | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
    shift
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo "Error: Invalid environment '$ENVIRONMENT'. Must be dev, staging, or prod."
    exit 1
fi

# Check for AWS credentials
if ! aws sts get-caller-identity &>/dev/null; then
    echo "Error: AWS credentials not configured. Please run 'aws configure' or set AWS_PROFILE."
    exit 1
fi

# Get AWS account info
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}

echo "=== Pantry Pirate Radio CDK Deployment ==="
echo "Environment: $ENVIRONMENT"
echo "AWS Account: $AWS_ACCOUNT"
echo "AWS Region:  $AWS_REGION"
echo "Action:      $ACTION"
echo ""

# Set CDK environment variables
export CDK_DEPLOY_ENVIRONMENT="$ENVIRONMENT"
export CDK_DEPLOY_ACCOUNT="$AWS_ACCOUNT"
export CDK_DEPLOY_REGION="$AWS_REGION"

# Change to infra directory
cd "$INFRA_DIR"

# Ensure dependencies are installed
if [[ ! -d ".venv" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Installing dependencies..."
source .venv/bin/activate
pip install -q -r requirements.txt

# Run CDK command
case $ACTION in
    deploy)
        echo ""
        echo "Deploying all stacks..."
        cdk deploy --all --require-approval broadening
        ;;
    diff)
        echo ""
        echo "Showing diff for all stacks..."
        cdk diff --all
        ;;
    synth)
        echo ""
        echo "Synthesizing templates..."
        cdk synth
        ;;
    destroy)
        echo ""
        echo "WARNING: This will destroy all infrastructure in $ENVIRONMENT!"
        read -p "Type 'yes' to confirm: " confirm
        if [[ "$confirm" == "yes" ]]; then
            cdk destroy --all --force
        else
            echo "Cancelled."
            exit 0
        fi
        ;;
esac

echo ""
echo "Done!"
