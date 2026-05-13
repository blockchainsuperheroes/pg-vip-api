"""
Pentagon VIP API — Unified endpoint for VIP tier resolution.

GET /user/vip — single source of truth.
Replaces 3-API client-side resolution with one call.
"""

import logging
from flask import Flask, request, jsonify

from config import Config
import resolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vip-api")

app = Flask(__name__)


# ─── Auth middleware ──────────────────────────────────────────

def check_auth():
    """Auth is optional. Keys still accepted but not required."""
    return True


# ─── Routes ───────────────────────────────────────────────────

@app.route("/user/vip_status", methods=["GET"])
def get_vip_status():
    """
    GET /user/vip_status

    Single source of truth for VIP status. Backend does everything:
    - Looks up user by wallet / username / discord_id
    - Source A: checks Discord roles from DB
    - Source B: queries Service API + BCSH API for all bound wallets
    - Evaluates thresholds, does max(rolesTier, onChainTier)
    - Returns flat JSON with everything in one shot

    Query params:
      wallet     - EVM address
      username   - PG username
      discord_id - Discord snowflake
    """
    if not check_auth():
        return jsonify({"status": False, "error": "Missing or invalid API key"}), 401

    wallet = request.args.get("wallet")
    username = request.args.get("username")
    discord_id = request.args.get("discord_id")

    if not any([wallet, username, discord_id]):
        return jsonify({
            "status": False,
            "error": "Provide at least one: wallet, username, or discord_id",
        }), 422

    try:
        result = resolver.resolve(
            wallet=wallet,
            username=username,
            discord_id=discord_id,
        )
    except Exception as e:
        logger.exception("VIP resolve failed")
        return jsonify({"status": False, "error": "Internal error during tier resolution"}), 500

    if result is None:
        return jsonify({"status": False, "error": "User not found"}), 404

    return jsonify({"status": True, "result": result})


# Keep /user/vip as alias during migration
@app.route("/user/vip", methods=["GET"])
def get_vip_status_alias():
    return get_vip_status()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "pg-vip-api"})


@app.route("/", methods=["GET"])
def index():
    """Service info."""
    return jsonify({
        "service": "Pentagon VIP API",
        "version": "1.1.0",
        "endpoint": "GET /user/vip_status",
        "docs": "https://blockchainsuperheroes.github.io/pg-role-bot-docs/",
        "params": {
            "wallet": "EVM address",
            "username": "PG username",
            "discord_id": "Discord snowflake ID",
        },
        "auth": "X-VIP-API-Key or X-PG-App-Key header",
    })


# ─── Run ──────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"Starting VIP API on {Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
