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
    """Verify API key or PG App Key."""
    api_key = request.headers.get("X-VIP-API-Key") or request.headers.get("X-PG-App-Key")
    if not api_key:
        return False
    # Accept our own VIP API key or a valid PG App Key (pk_live_*)
    if api_key == Config.VIP_API_KEY:
        return True
    if api_key.startswith("pk_live_"):
        return True
    return False


# ─── Routes ───────────────────────────────────────────────────

@app.route("/user/vip", methods=["GET"])
def get_vip_status():
    """
    GET /user/vip

    Single source of truth for VIP status. Backend does everything:
    - Looks up user by wallet / username / discord_id
    - Source A: checks Discord roles from DB
    - Source B: queries Service API + BCSH API for all bound wallets
    - Evaluates thresholds, does max(rolesTier, onChainTier)
    - Returns clean JSON with correct referral rate

    Query params:
      wallet     - EVM address
      username   - PG username
      discord_id - Discord snowflake
      include    - comma-separated: balances,nfts,roles,wallets,progress
    """
    if not check_auth():
        return jsonify({"status": False, "error": "Missing or invalid API key"}), 401

    wallet = request.args.get("wallet")
    username = request.args.get("username")
    discord_id = request.args.get("discord_id")
    include_raw = request.args.get("include", "")
    includes = [s.strip() for s in include_raw.split(",") if s.strip()]

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
            includes=includes,
        )
    except Exception as e:
        logger.exception("VIP resolve failed")
        return jsonify({"status": False, "error": "Internal error during tier resolution"}), 500

    if result is None:
        return jsonify({"status": False, "error": "User not found"}), 404

    return jsonify({"status": True, "result": result})


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "pg-vip-api"})


@app.route("/", methods=["GET"])
def index():
    """Service info."""
    return jsonify({
        "service": "Pentagon VIP API",
        "version": "1.0.0",
        "endpoint": "GET /user/vip",
        "docs": "https://blockchainsuperheroes.github.io/pg-role-bot-docs/",
        "params": {
            "wallet": "EVM address",
            "username": "PG username",
            "discord_id": "Discord snowflake ID",
            "include": "comma-separated: balances, nfts, roles, wallets, progress",
        },
        "auth": "X-VIP-API-Key or X-PG-App-Key header",
    })


# ─── Run ──────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(f"Starting VIP API on {Config.HOST}:{Config.PORT}")
    app.run(host=Config.HOST, port=Config.PORT, debug=False)
