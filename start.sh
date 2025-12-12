#!/bin/sh
# Startup script for Railway deployment
# Railway sets PORT environment variable automatically
PORT=${PORT:-8080}
exec gunicorn app:app --workers=2 --threads=4 --bind=0.0.0.0:$PORT

