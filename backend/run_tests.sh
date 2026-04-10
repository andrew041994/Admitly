#!/usr/bin/env bash

export DATABASE_URL="postgresql://neondb_owner:npg_jKSZablLD72J@ep-proud-truth-any41xfp-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

echo "Running migrations..."
alembic upgrade head

echo "Running tests..."
PYTHONPATH=. python -m pytest

unset DATABASE_URL