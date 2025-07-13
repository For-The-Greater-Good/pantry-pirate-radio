"""Constants used across test files"""

from typing import Final

# Disable real model requests during testing
ALLOW_MODEL_REQUESTS: Final[bool] = False

# Default model name for testing
TEST_MODEL_NAME: Final[str] = "mistralai/vanilj/phi-4-unslot:latest-24b-instruct-2501"

# Test API keys
TEST_API_KEY: Final[str] = "test-key"
TEST_API_KEY_ARG: Final[str] = "test-key-arg"

# Test URLs
TEST_CUSTOM_URL: Final[str] = "https://custom.url"

# Test error messages
TEST_RATE_LIMIT_ERROR: Final[str] = "rate_limit_exceeded"
TEST_INVALID_MODEL_ERROR: Final[str] = "invalid_model"
TEST_CONTEXT_LENGTH_ERROR: Final[str] = "context_length_exceeded"

# Test model configurations
TEST_CONTEXT_LENGTH: Final[int] = 8192
TEST_MAX_TOKENS: Final[int] = 64768
TEST_DEFAULT_TEMP: Final[float] = 0.7
TEST_RETRIES: Final[int] = 3
TEST_RETRY_DELAY: Final[float] = 1.0

# Test file paths
TEST_SCHEMA_CONTENT: Final[
    str
] = """table_name,name,type,description,constraints_unique,constraints_required,constraints_tablular_required,format,one_to_many,one_to_one,enum
organization,id,string,Organization identifier,true,true,false,,,,
organization,name,string,Organization name,false,true,false,,,,
organization,services,array,Organization services,false,true,false,,service.json,,
service,id,string,Service identifier,true,true,false,,,,
service,name,string,Service name,false,true,false,,,,
service,organization_id,string,Organization providing service,false,true,false,,,,
service,status,string,Service status,false,true,false,,,,active,inactive
location,id,string,Location identifier,true,true,false,,,,
location,name,string,Location name,false,true,false,,,,
location,address,object,Location address,false,true,false,,,,
"""
