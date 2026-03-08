"""CloudFormation Custom Resource handler for database initialization trigger.

CRITICAL: This handler ONLY starts the state machine on CREATE events.
UPDATE and DELETE events are acknowledged but do nothing.
"""

import json  # noqa: F401 — available in Lambda runtime
import os

import boto3


def handler(event, context):
    """Handle CloudFormation Custom Resource events.

    CRITICAL SAFETY: Only starts state machine on CREATE.
    UPDATE and DELETE are no-ops to prevent re-initialization.
    """
    request_type = event["RequestType"]
    print(f"Received {request_type} request")

    if request_type == "Create":
        # Only trigger on first deployment
        sfn = boto3.client("stepfunctions")
        response = sfn.start_execution(
            stateMachineArn=os.environ["STATE_MACHINE_ARN"],
            name=f"init-{context.aws_request_id[:8]}",
        )
        print(f"Started state machine execution: {response['executionArn']}")
        return {
            "PhysicalResourceId": response["executionArn"],
            "Data": {"ExecutionArn": response["executionArn"]},
        }
    elif request_type == "Update":
        # CRITICAL: Do nothing on update - this prevents re-initialization
        print("Update event received - no action taken (safety mechanism)")
        return {
            "PhysicalResourceId": event.get("PhysicalResourceId", "no-init"),
        }
    elif request_type == "Delete":
        # Nothing to clean up - just acknowledge
        print("Delete event received - no action taken")
        return {
            "PhysicalResourceId": event.get("PhysicalResourceId", "deleted"),
        }

    return {"PhysicalResourceId": "unknown"}
