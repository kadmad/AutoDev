#!/bin/bash
set -e

echo "=== AutoDev Startup ==="

# 1. Start infrastructure
echo "[1/4] Starting PostgreSQL + Redis..."
docker-compose up -d
sleep 3

# 2. Start backend
echo "[2/4] Starting FastAPI backend (port 8000)..."
cd backend
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  Created .env from .env.example — please edit with real values"
fi

if [ ! -d "venv" ]; then
  python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt -q
fi

./venv/bin/uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID"
cd ..

# 3. Start rq worker
echo "[3/4] Starting pipeline worker..."
cd backend
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ./venv/bin/rq worker pipeline:default pipeline:agents --url redis://localhost:6379 &
WORKER_PID=$!
echo "  Worker PID: $WORKER_PID"
cd ..

# 4. Start frontend
echo "[4/4] Starting React frontend (port 3000)..."
cd frontend
if [ ! -d "node_modules" ]; then
  npm install -q
fi
npm run dev &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID"
cd ..

echo ""
echo "=== AutoDev Running ==="
echo "  UI:      http://localhost:3000"
echo "  API:     http://localhost:8000"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"

trap "kill $BACKEND_PID $WORKER_PID $FRONTEND_PID 2>/dev/null; docker-compose stop; echo 'Stopped.'" EXIT

wait $BACKEND_PID
