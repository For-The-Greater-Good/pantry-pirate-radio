#!/bin/bash
# Bootstrap CDK for Pantry Pirate Radio
#
# This script performs one-time setup tasks:
# 1. Bootstraps CDK in the target AWS account/region
# 2. Creates ECR repositories for container images
# 3. Sets up required IAM roles for GitHub Actions
#
# Usage:
#   ./scripts/bootstrap.sh [environment]
#
# Requirements:
#   - AWS CLI configured with admin credentials
#   - CDK installed (npm install -g aws-cdk)

set -euo pipefail

ENVIRONMENT="${1:-dev}"

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|prod)$ ]]; then
    echo "Error: Invalid environment '$ENVIRONMENT'. Must be dev, staging, or prod."
    exit 1
fi

# Check for AWS credentials
if ! aws sts get-caller-identity &>/dev/null; then
    echo "Error: AWS credentials not configured."
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=${AWS_REGION:-us-east-1}

echo "=== Pantry Pirate Radio CDK Bootstrap ==="
echo "Environment: $ENVIRONMENT"
echo "AWS Account: $AWS_ACCOUNT"
echo "AWS Region:  $AWS_REGION"
echo ""

# Bootstrap CDK
echo "Bootstrapping CDK..."
cdk bootstrap "aws://$AWS_ACCOUNT/$AWS_REGION" \
    --cloudformation-execution-policies arn:aws:iam::aws:policy/AdministratorAccess \
    --trust "$AWS_ACCOUNT"

# Create ECR repositories
echo ""
echo "Creating ECR repositories..."

for repo_suffix in "app" "worker" "validator" "reconciler" "recorder" "api-lambda" "publisher" "batch-lambda" "scraper"; do
    REPO_NAME="pantry-pirate-radio-${repo_suffix}-${ENVIRONMENT}"

    if aws ecr describe-repositories --repository-names "$REPO_NAME" &>/dev/null; then
        echo "  Repository $REPO_NAME already exists"
    else
        echo "  Creating repository $REPO_NAME..."
        aws ecr create-repository \
            --repository-name "$REPO_NAME" \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=AES256
    fi
done

# Create GitHub Actions OIDC provider (if not exists)
echo ""
echo "Setting up GitHub Actions OIDC provider..."

OIDC_PROVIDER_ARN=$(aws iam list-open-id-connect-providers --query \
    "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" \
    --output text)

if [[ -z "$OIDC_PROVIDER_ARN" ]]; then
    echo "  Creating OIDC provider for GitHub Actions..."
    aws iam create-open-id-connect-provider \
        --url "https://token.actions.githubusercontent.com" \
        --client-id-list "sts.amazonaws.com" \
        --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1"
    OIDC_PROVIDER_ARN=$(aws iam list-open-id-connect-providers --query \
        "OpenIDConnectProviderList[?contains(Arn, 'token.actions.githubusercontent.com')].Arn" \
        --output text)
fi

echo "  OIDC Provider ARN: $OIDC_PROVIDER_ARN"

# Create deployment role for GitHub Actions
ROLE_NAME="pantry-pirate-radio-deploy-${ENVIRONMENT}"

echo ""
echo "Creating GitHub Actions deployment role..."

TRUST_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "$OIDC_PROVIDER_ARN"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:For-The-Greater-Good/pantry-pirate-radio:*"
                }
            }
        }
    ]
}
EOF
)

if aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
    echo "  Role $ROLE_NAME already exists, updating trust policy..."
    aws iam update-assume-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-document "$TRUST_POLICY"
else
    echo "  Creating role $ROLE_NAME..."
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY"
fi

# Attach required policies
echo "  Attaching policies..."
aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser

# NOTE: Previously used *FullAccess managed policies (ECS, S3, DynamoDB, SQS)
# are replaced by the scoped inline policy below.

# Create inline policy for CDK deployment and service management
# Scoped to pantry-pirate-radio-* resources where possible.
# Some actions (CloudFormation, EC2, IAM for CDK) require resource=* due to
# CDK's bootstrapping and cross-stack reference patterns.
CDK_POLICY=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CDKBootstrapAndDeploy",
            "Effect": "Allow",
            "Action": [
                "cloudformation:*",
                "ssm:GetParameter",
                "ssm:PutParameter"
            ],
            "Resource": "*"
        },
        {
            "Sid": "CDKRoleAssumption",
            "Effect": "Allow",
            "Action": "sts:AssumeRole",
            "Resource": "arn:aws:iam::$AWS_ACCOUNT:role/cdk-*"
        },
        {
            "Sid": "ECSServiceManagement",
            "Effect": "Allow",
            "Action": [
                "ecs:UpdateService",
                "ecs:DescribeServices",
                "ecs:DescribeClusters",
                "ecs:ListServices"
            ],
            "Resource": [
                "arn:aws:ecs:$AWS_REGION:$AWS_ACCOUNT:cluster/pantry-pirate-radio-*",
                "arn:aws:ecs:$AWS_REGION:$AWS_ACCOUNT:service/pantry-pirate-radio-*/*"
            ]
        },
        {
            "Sid": "LambdaManagement",
            "Effect": "Allow",
            "Action": [
                "lambda:UpdateFunctionCode",
                "lambda:ListFunctions",
                "lambda:GetFunction"
            ],
            "Resource": "arn:aws:lambda:$AWS_REGION:$AWS_ACCOUNT:function:*"
        },
        {
            "Sid": "SecretsManagerRead",
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": "arn:aws:secretsmanager:$AWS_REGION:$AWS_ACCOUNT:secret:pantry-pirate-radio-*"
        },
        {
            "Sid": "ECRAccess",
            "Effect": "Allow",
            "Action": "ecr:*",
            "Resource": "arn:aws:ecr:$AWS_REGION:$AWS_ACCOUNT:repository/pantry-pirate-radio-*"
        },
        {
            "Sid": "CDKInfrastructure",
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole",
                "iam:AttachRolePolicy",
                "iam:PassRole",
                "iam:PutRolePolicy",
                "iam:GetRole",
                "iam:DeleteRolePolicy",
                "iam:DeleteRole",
                "iam:TagRole",
                "iam:CreateServiceLinkedRole",
                "iam:DetachRolePolicy",
                "iam:ListRolePolicies",
                "iam:ListAttachedRolePolicies",
                "iam:CreateInstanceProfile",
                "iam:DeleteInstanceProfile",
                "iam:AddRoleToInstanceProfile",
                "iam:RemoveRoleFromInstanceProfile",
                "iam:GetInstanceProfile",
                "iam:ListInstanceProfilesForRole",
                "ec2:*",
                "elasticloadbalancing:*",
                "logs:*",
                "sns:*",
                "cloudwatch:*",
                "application-autoscaling:*",
                "s3:*",
                "dynamodb:*",
                "sqs:*"
            ],
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "aws:RequestedRegion": "$AWS_REGION"
                }
            }
        }
    ]
}
EOF
)

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "CDKDeployPolicy" \
    --policy-document "$CDK_POLICY"

ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text)

echo ""
echo "=== Bootstrap Complete ==="
echo ""
echo "GitHub Actions configuration:"
echo "  Add these secrets to your repository:"
echo ""
echo "  AWS_DEPLOY_ROLE_ARN: $ROLE_ARN"
echo "  AWS_ACCOUNT_ID: $AWS_ACCOUNT"
echo ""
echo "Next steps:"
echo "  1. Add the secrets above to GitHub repository settings"
echo "  2. Run './scripts/deploy.sh $ENVIRONMENT' to deploy infrastructure"
echo ""
