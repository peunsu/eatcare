#!/usr/bin/env bash
# 서버 기동 (백그라운드). 포트 80은 root 권한 필요 → sudo 사용. 로그: ~/workspace/server.log
set -e
source ~/miniconda3/etc/profile.d/conda.sh
conda activate db
UVICORN="$(command -v uvicorn)"
PORT="${PORT:-80}"
WORKDIR="$HOME/workspace"
LOG="$WORKDIR/server.log"

sudo pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1
# sudo로 root 쉘을 띄워 그 안에서 detach(setsid+nohup+&) → sudo는 즉시 반환
sudo bash -c "cd '$WORKDIR' && setsid nohup '$UVICORN' app.main:app --host 0.0.0.0 --port $PORT > '$LOG' 2>&1 < /dev/null &"
echo "started on port $PORT (uvicorn: $UVICORN)"
sleep 4
echo "--- log ---"
tail -n 12 "$LOG"
