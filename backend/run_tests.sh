#!/usr/bin/env bash

: "${TEST_DATABASE_URL:?Set TEST_DATABASE_URL to an isolated test database.}"
export DATABASE_URL="$TEST_DATABASE_URL"

echo "Running migrations..."
alembic upgrade head

echo "Running tests..."
PYTHONPATH=. python -m pytest

unset DATABASE_URL
