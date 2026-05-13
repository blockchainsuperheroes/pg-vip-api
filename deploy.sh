#!/bin/bash
# Deploy pg-vip-api to pg-identity-be (13.212.154.41)
# Run from the repo root on your local machine.

set -e

SERVER="ubuntu@13.212.154.41"
DEPLOY_DIR="/var/www/services/pg-vip-api"

echo "=== Deploying pg-vip-api ==="

# 1. Create directory on server
ssh $SERVER "sudo mkdir -p $DEPLOY_DIR && sudo chown ubuntu:ubuntu $DEPLOY_DIR"

# 2. Sync files
rsync -avz --exclude '.git' --exclude 'venv' --exclude '__pycache__' --exclude '.env' \
  ./ $SERVER:$DEPLOY_DIR/

# 3. Set up virtualenv + install deps
ssh $SERVER "cd $DEPLOY_DIR && python3 -m venv venv && venv/bin/pip install -r requirements.txt"

# 4. Copy .env if it doesn't exist yet
ssh $SERVER "test -f $DEPLOY_DIR/.env || cp $DEPLOY_DIR/.env.example $DEPLOY_DIR/.env"
echo "⚠️  Edit .env on server: ssh $SERVER 'nano $DEPLOY_DIR/.env'"

# 5. Install supervisor config
ssh $SERVER "sudo cp $DEPLOY_DIR/supervisor.conf /etc/supervisor/conf.d/pg-vip-api.conf"

# 6. Reload supervisor
ssh $SERVER "sudo supervisorctl reread && sudo supervisorctl update && sudo supervisorctl restart pg-vip-api"

# 7. Check status
sleep 2
ssh $SERVER "sudo supervisorctl status pg-vip-api"
ssh $SERVER "curl -s http://localhost:9022/health"

echo ""
echo "=== Deployed! ==="
echo "Internal: http://localhost:9022/user/vip"
echo "Next: Edit .env with real DB password and API keys"
