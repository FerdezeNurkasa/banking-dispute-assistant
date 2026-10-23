"""AWS Lambda entry point: Mangum translates API Gateway events into ASGI requests for FastAPI."""
from mangum import Mangum

from app.main import app

handler = Mangum(app, lifespan="auto")