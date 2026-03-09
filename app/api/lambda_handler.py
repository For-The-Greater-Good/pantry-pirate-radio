"""AWS Lambda handler for the API via Mangum."""

from mangum import Mangum

from app.api.lambda_app import app

handler = Mangum(app, lifespan="off")
