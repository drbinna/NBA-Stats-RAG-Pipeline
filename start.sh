#!/bin/bash
cd backend
exec python -m uvicorn server:app --host 0.0.0.0 --port "${PORT:-10000}"
