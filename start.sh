#!/bin/bash
set -e

# Load .env if it exists
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi

# Start Vite frontend on 5173 first (so it's warming up while backend starts)
npx vite --port 5173 --host 0.0.0.0 &
FRONTEND_PID=$!

# Start Python FastAPI backend on port 5000
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 5000 --reload &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Waiting for Python backend on port 5000..."
for i in $(seq 1 30); do
  if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "Python backend ready!"
    break
  fi
  sleep 1
done

# Wait for Vite frontend to be ready
echo "Waiting for Vite frontend on port 5173..."
for i in $(seq 1 30); do
  if curl -s http://localhost:5173/ > /dev/null 2>&1; then
    echo "Vite frontend ready!"
    break
  fi
  sleep 1
done

# Trap signals to kill both processes
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM EXIT

wait $BACKEND_PID $FRONTEND_PID
