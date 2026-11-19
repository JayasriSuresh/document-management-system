#!/bin/bash
# ═══════════════════════════════════════════════════
# DMS Prototype — Quick Start Script
# ═══════════════════════════════════════════════════

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   DMS Prototype — Starting up...        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 0. Pre-flight checks & PostgreSQL ─────────────────────────
echo "▶ Checking PostgreSQL cluster on port 5434..."
if ! pg_isready -h /tmp -p 5434 >/dev/null 2>&1; then
  echo "  Starting local PostgreSQL from .pgdata..."
  /usr/lib/postgresql/17/bin/postgres -D "$PROJECT_DIR/.pgdata" -p 5434 -k /tmp > "$PROJECT_DIR/.pgdata/postgres.log" 2>&1 &
  sleep 2
fi
echo "  PostgreSQL OK ✓"

# ── 1. Python venv ──────────────────────────────────
echo ""
echo "▶ Setting up Python backend..."
cd "$BACKEND_DIR"
if [ ! -d "venv" ]; then
  echo "  Creating virtual environment..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -q -r requirements.txt
else
  source venv/bin/activate
fi
echo "  Python environment OK ✓"

# ── 2. Run Migrations ────────────────────────────────
echo ""
echo "▶ Running database migrations..."
alembic upgrade head

# ── 4. Start FastAPI & Worker ────────────────────────────
echo ""
echo "▶ Starting FastAPI backend on :8000..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
python3 -m app.worker &
WORKER_PID=$!
sleep 2

# ── 5. Start React frontend ──────────────────────
echo ""
echo "▶ Starting React frontend on :5173..."
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!
sleep 2

# ── Done ─────────────────────────────────────────
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  ✅ DMS Prototype is running!                       ║"
echo "║                                                      ║"
echo "║  Frontend:  http://localhost:5173                   ║"
echo "║  Backend:   http://localhost:8000                   ║"
echo "║  API Docs:  http://localhost:8000/docs              ║"
echo "║                                                      ║"
echo "║  📱 Phone access (same WiFi):                       ║"
echo "║  http://${LAN_IP}:5173                   ║"
echo "║                                                      ║"
echo "║  Press Ctrl+C to stop all services                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Wait for Ctrl+C and cleanup
trap "echo ''; echo 'Stopping all services...'; kill $BACKEND_PID $FRONTEND_PID $WORKER_PID 2>/dev/null; echo 'Done. Goodbye!'" INT TERM

wait
