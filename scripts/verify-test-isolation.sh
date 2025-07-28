#!/bin/bash
# Script to verify test isolation is properly configured

echo "=== Verifying Test Isolation Configuration ==="
echo

# Check environment variables
echo "1. Checking environment variables..."

# For dev container, use the correct values
if [ -z "$TEST_DATABASE_URL" ]; then
    echo "⚠️  TEST_DATABASE_URL is not set in environment"
    export TEST_DATABASE_URL="postgresql+psycopg2://postgres:your_secure_password@db:5432/test_pantry_pirate_radio"
    echo "   Using default: $TEST_DATABASE_URL"
else
    echo "✅ TEST_DATABASE_URL is set: $TEST_DATABASE_URL"
fi

if [ -z "$TEST_REDIS_URL" ]; then
    echo "⚠️  TEST_REDIS_URL is not set in environment"
    export TEST_REDIS_URL="redis://cache:6379/1"
    echo "   Using default: $TEST_REDIS_URL"
else
    echo "✅ TEST_REDIS_URL is set: $TEST_REDIS_URL"
fi

# Check if test URLs are different from production
if [ "$DATABASE_URL" = "$TEST_DATABASE_URL" ]; then
    echo "❌ CRITICAL: TEST_DATABASE_URL is the same as DATABASE_URL!"
    echo "   This could lead to production data loss!"
    exit 1
else
    echo "✅ Test database is different from production database"
fi

if [ "$REDIS_URL" = "$TEST_REDIS_URL" ]; then
    echo "❌ CRITICAL: TEST_REDIS_URL is the same as REDIS_URL!"
    echo "   This could lead to production data loss!"
    exit 1
else
    echo "✅ Test Redis is different from production Redis"
fi

echo
echo "2. Checking test database exists..."
# Extract database name from TEST_DATABASE_URL
TEST_DB_NAME=$(echo $TEST_DATABASE_URL | sed -n 's/.*\/\([^?]*\).*/\1/p')
export PGPASSWORD="your_secure_password"
if psql -U postgres -h db -lqt | cut -d \| -f 1 | grep -qw "$TEST_DB_NAME"; then
    echo "✅ Test database '$TEST_DB_NAME' exists"
else
    echo "❌ Test database '$TEST_DB_NAME' does not exist"
    echo "   Create it with: psql -U postgres -h db -c \"CREATE DATABASE $TEST_DB_NAME\""
fi
unset PGPASSWORD

echo
echo "3. Testing Redis isolation..."
python3 -c "
import redis
import sys

try:
    # Test Redis connection
    test_redis = redis.from_url('$TEST_REDIS_URL')
    test_redis.ping()

    # Check database number
    redis_db = '$TEST_REDIS_URL'.split('/')[-1]
    if redis_db == '0':
        print('⚠️  WARNING: Using Redis database 0 for tests (same as production default)')
        print('   Consider using database 1 or higher for better isolation')
    else:
        print(f'✅ Using Redis database {redis_db} for tests (isolated from default 0)')

    # Test key prefix functionality
    test_key = 'test:verify:test_key'
    test_redis.set(test_key, 'test_value')
    if test_redis.get(test_key) == b'test_value':
        print('✅ Redis test keys are working correctly')
        test_redis.delete(test_key)
    else:
        print('❌ Redis test key storage failed')
        sys.exit(1)

except Exception as e:
    print(f'❌ Redis test failed: {e}')
    sys.exit(1)
"

echo
echo "4. Running a simple test to verify fixtures..."
poetry run pytest tests/test_api_endpoints_unit.py::TestOrganizationsEndpoints::test_list_organizations_function_logic -q
if [ $? -eq 0 ]; then
    echo "✅ Test fixture is working correctly"
else
    echo "❌ Test fixture failed - check the error above"
fi

echo
echo "=== Test Isolation Verification Complete ==="
echo
echo "If all checks pass, your test environment is properly isolated from production!"