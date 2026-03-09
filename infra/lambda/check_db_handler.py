"""Lambda handler to check if database initialization is needed.

Checks the SSM parameter to determine if the database has already
been initialized. Used by the db-init Step Functions state machine.
"""

import os

import boto3


def handler(event, context):
    """Check if database initialization is needed via SSM parameter.

    The SSM parameter tracks whether init has run. On first deploy it is
    "false", so init will be triggered. After successful init, the Step
    Functions state machine sets it to "true".

    Returns:
        dict with needs_init: True if initialization is needed
    """
    ssm = boto3.client("ssm")

    try:
        response = ssm.get_parameter(
            Name=os.environ["SSM_PARAMETER_NAME"]
        )
        if response["Parameter"]["Value"] == "true":
            print("SSM flag indicates DB already initialized")
            return {"needs_init": False}
        else:
            print("SSM flag is not true, initialization needed")
            return {"needs_init": True}
    except ssm.exceptions.ParameterNotFound:
        print("SSM parameter not found, initialization needed")
        return {"needs_init": True}
    except Exception as e:
        print(f"Unexpected error checking SSM parameter: {e}")
        raise  # Let Step Functions handle the error — do NOT assume init is needed
