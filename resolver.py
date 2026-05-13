"""
TierResolver — Single source of truth for VIP tier determination.

Encapsulates ALL tier logic. Every consumer calls this.
No more client-side Math.max across 3 APIs.

Two sources:
  Source A: Discord roles stored in DB (synced by role bot every 4h)
  Source B: On-chain holdings (PEN + ZOR balances, NFTs)
  effectiveTier = max(sourceA, sourceB)
"""

import logging
import httpx

import db
from config import Config

logger = logging.getLogger(__name__)

# ─── Thresholds ──────────────────────────────────────────────

# VIP3: 5M PEN OR Ethan NFT (Ethereum) OR Obelith Setsuko (on-chain tier 2)
# VIP2: 1M PEN OR 50K ZOR OR any Chain Hero NFT
# VIP1: 200K PEN OR 10K ZOR OR any BCSH NFT
THRESHOLDS = {
    3: {"pen": 5_000_000, "zor": None},
    2: {"pen": 1_000_000, "zor": 50_000},
    1: {"pen": 200_000, "zor": 10_000},
}

CHAIN_HERO_NAMES = {"Setsuko", "Lazuli", "Avyaan", "Launch", "Nomad", "BCSH CORE"}

REFERRAL_RATES = {
    0: 0.00,   # Newcomer — nothing
    1: 0.00,   # VIP1 — display only, no payout
    2: 0.05,   # VIP2 — 5%
    3: 0.15,   # VIP3 — 15%
}

TIER_NAMES = {0: "Newcomer", 1: "VIP1", 2: "VIP2", 3: "VIP3"}

# Setsuko on-chain tier constants
SETSUKO_CHAIN_PREFIX = "5555"
TOKEN_TIER_SELECTOR = "0x649e705f"  # keccak256("tokenTier(uint256)")[:4]
BALANCEOF_SELECTOR = "0x70a08231"   # balanceOf(address)


# ─── User lookup ──────────────────────────────────────────────

def lookup_user(wallet=None, username=None, discord_id=None):
    """Find user in pg_identity_db by wallet, username, or discord_id."""
    if wallet:
        row = db.query_one(
            'SELECT id, username, email, mm_address, verified FROM "user" WHERE LOWER(mm_address) = LOWER(%s) AND is_deleted = FALSE',
            (wallet,),
        )
        if row:
            return row

    if username:
        row = db.query_one(
            'SELECT id, username, email, mm_address, verified FROM "user" WHERE username = %s AND is_deleted = FALSE',
            (username,),
        )
        if not row:
            # Try legacy username
            row = db.query_one(
                """SELECT u.id, u.username, u.email, u.mm_address, u.verified
                   FROM "user" u
                   JOIN user_legacy_username l ON l.user_id = u.id
                   WHERE l.username = %s AND u.is_deleted = FALSE""",
                (username,),
            )
        if row:
            return row

    if discord_id:
        row = db.query_one(
            """SELECT u.id, u.username, u.email, u.mm_address, u.verified
               FROM "user" u
               JOIN user_social_accounts s ON s.user_id = u.id
               JOIN social_platforms p ON s.platform_id = p.id
               WHERE p.slug = 'discord' AND p.is_active = TRUE
                 AND s.external_id = %s AND u.is_deleted = FALSE""",
            (str(discord_id),),
        )
        if row:
            return row

    return None


def get_all_wallets(user_id):
    """Get all bound EVM wallet addresses for a user."""
    wallets = set()

    # Primary wallet
    row = db.query_one('SELECT mm_address FROM "user" WHERE id = %s', (user_id,))
    if row and row.get("mm_address"):
        wallets.add(row["mm_address"].lower())

    # External wallets (metamask type)
    rows = db.query_all(
        """SELECT address FROM user_external_wallets
           WHERE user_id = %s AND wallet_type = 'metamask'""",
        (user_id,),
    )
    for r in rows:
        if r.get("address"):
            wallets.add(r["address"].lower())

    return list(wallets)


# ─── Source A: Discord roles from DB ──────────────────────────

def get_discord_role_tier(user_id):
    """Check user_discord_roles table for VIP tier. Returns (tier_int, roles_list)."""
    row = db.query_one(
        "SELECT roles, sub_roles FROM user_discord_roles WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    )
    if not row or not row.get("roles"):
        return 0, [], []

    roles = [r.strip() for r in row["roles"].split(",") if r.strip()]
    sub_roles = [r.strip() for r in (row.get("sub_roles") or "").split(",") if r.strip()]

    tier = 0
    if "VIP3" in roles:
        tier = 3
    elif "VIP2" in roles:
        tier = 2
    elif "VIP1" in roles:
        tier = 1

    return tier, roles, sub_roles


# ─── Source B: On-chain holdings ──────────────────────────────

def fetch_pen_balance_api(address):
    """PEN balance from Service API (ETH + Arbitrum)."""
    try:
        url = f"{Config.SERVICE_API_URL}/balance/pen/{address}"
        headers = {"api-key": Config.SERVICE_API_KEY}
        r = httpx.get(url, headers=headers, timeout=Config.HTTP_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            balance = data.get("balance", 0) or 0
            chain_balance = data.get("chain_balance", {})
            return {
                "api_total": float(balance),
                "ethereum": float(chain_balance.get("ethereum", 0) or 0),
                "arbitrum": float(chain_balance.get("arb", 0) or 0),
            }
    except Exception as e:
        logger.error(f"PEN API error for {address}: {e}")
    return {"api_total": 0, "ethereum": 0, "arbitrum": 0}


def fetch_pen_balance_onchain(address):
    """PEN ERC-20 balance on Pentagon Chain via direct RPC call."""
    try:
        padded = address.lower().replace("0x", "").zfill(64)
        data = BALANCEOF_SELECTOR + padded
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": Config.PEN_PC_CONTRACT, "data": data}, "latest"],
            "id": 1,
        }
        r = httpx.post(Config.PENTAGON_RPC, json=payload, timeout=Config.HTTP_TIMEOUT)
        if r.status_code == 200:
            result = r.json().get("result", "0x0")
            if result and result != "0x":
                raw = int(result, 16)
                return raw / 1e18
    except Exception as e:
        logger.error(f"PEN on-chain error for {address}: {e}")
    return 0


def fetch_zor_balance(address):
    """ZOR balance from Service API."""
    try:
        url = f"{Config.SERVICE_API_URL}/balance/zor/{address}"
        headers = {"api-key": Config.SERVICE_API_KEY}
        r = httpx.get(url, headers=headers, timeout=Config.HTTP_TIMEOUT)
        if r.status_code == 200:
            return float(r.json().get("balance", 0) or 0)
    except Exception as e:
        logger.error(f"ZOR API error for {address}: {e}")
    return 0


def fetch_bcsh_nfts(address):
    """BCSH NFTs from api.bcsh.xyz with pagination. Returns (count, names_set, items_list)."""
    all_items = []
    all_names = set()
    total = 0
    page = 1

    try:
        while True:
            url = f"{Config.BCSH_API_URL}/user/nfts/{address}?page={page}"
            r = httpx.get(url, timeout=Config.HTTP_TIMEOUT)
            if r.status_code != 200:
                break
            result = r.json().get("result", {})
            total = int(result.get("total_item", 0))
            total_pages = int(result.get("total_page", 1))
            items = result.get("items", [])
            all_items.extend(items)
            all_names.update(
                item.get("name", "").strip() for item in items if item.get("name")
            )
            if page >= total_pages:
                break
            page += 1
    except Exception as e:
        logger.error(f"BCSH NFT error for {address}: {e}")

    return total, all_names, all_items


def fetch_ethan_nfts(address):
    """Ethan NFTs on Ethereum (chain_id=1)."""
    try:
        url = f"{Config.BCSH_API_URL}/user/nfts/{address}?chain_id=1"
        r = httpx.get(url, timeout=Config.HTTP_TIMEOUT)
        if r.status_code == 200:
            result = r.json().get("result", {})
            count = int(result.get("total_item", 0))
            return count > 0, count
    except Exception as e:
        logger.error(f"Ethan NFT error for {address}: {e}")
    return False, 0


def check_setsuko_tier_onchain(token_id_str):
    """Call tokenTier(tokenId) on Setsuko distributor. Returns 0/1/2 (normal/dark/obelith)."""
    try:
        actual_id = token_id_str
        if token_id_str.startswith(SETSUKO_CHAIN_PREFIX):
            actual_id = str(int(token_id_str[len(SETSUKO_CHAIN_PREFIX):]))

        token_int = int(actual_id)
        data = TOKEN_TIER_SELECTOR + hex(token_int)[2:].zfill(64)
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": Config.SETSUKO_DISTRIBUTOR, "data": data}, "latest"],
            "id": 1,
        }
        r = httpx.post(Config.PENTAGON_RPC, json=payload, timeout=Config.HTTP_TIMEOUT)
        if r.status_code == 200:
            result = r.json().get("result", "0x")
            if result and result != "0x":
                return int(result, 16)
    except Exception as e:
        logger.error(f"Setsuko tier check failed for {token_id_str}: {e}")
    return 0


def check_setsuko_tiers(nft_items):
    """Check all Setsuko NFTs for on-chain tier. Returns (has_obelith, has_dark)."""
    has_obelith = False
    has_dark = False
    for item in nft_items:
        name = item.get("name", "")
        token_id = str(item.get("token_id", ""))
        if name == "Setsuko" and token_id.startswith(SETSUKO_CHAIN_PREFIX):
            tier = check_setsuko_tier_onchain(token_id)
            if tier == 2:
                has_obelith = True
            elif tier == 1:
                has_dark = True
            if has_obelith:
                break
    return has_obelith, has_dark


# ─── Aggregate on-chain data ─────────────────────────────────

def collect_onchain_holdings(wallets):
    """Query all APIs for all wallets. Returns aggregated holdings dict."""
    total_pen = 0.0
    total_zor = 0.0
    total_bcsh = 0
    has_ethan = False
    ethan_count = 0
    has_chain_hero = False
    has_obelith = False
    has_dark = False
    all_nft_names = set()
    all_nft_items = []
    pen_by_chain = {"pentagon": 0.0, "ethereum": 0.0, "arbitrum": 0.0}

    for addr in wallets:
        # PEN: API (ETH + ARB) + on-chain (Pentagon Chain)
        pen_api = fetch_pen_balance_api(addr)
        pen_pc = fetch_pen_balance_onchain(addr)
        wallet_pen = pen_api["api_total"] + pen_pc
        total_pen += wallet_pen
        pen_by_chain["pentagon"] += pen_pc
        pen_by_chain["ethereum"] += pen_api["ethereum"]
        pen_by_chain["arbitrum"] += pen_api["arbitrum"]

        # ZOR
        total_zor += fetch_zor_balance(addr)

        # BCSH NFTs (Pentagon Chain)
        bcsh_count, nft_names, nft_items = fetch_bcsh_nfts(addr)
        total_bcsh += bcsh_count
        all_nft_names.update(nft_names)
        all_nft_items.extend(nft_items)

        # Ethan NFTs (Ethereum)
        wallet_ethan, wallet_ethan_count = fetch_ethan_nfts(addr)
        if wallet_ethan:
            has_ethan = True
        ethan_count += wallet_ethan_count

    # Chain Hero check
    has_chain_hero = bool(all_nft_names & CHAIN_HERO_NAMES)

    # Setsuko on-chain tier check
    if "Setsuko" in all_nft_names:
        try:
            has_obelith, has_dark = check_setsuko_tiers(all_nft_items)
        except Exception as e:
            logger.error(f"Setsuko tier check failed: {e}")

    return {
        "pen": total_pen,
        "zor": total_zor,
        "pen_by_chain": pen_by_chain,
        "bcsh_count": total_bcsh,
        "has_bcsh": total_bcsh > 0,
        "has_ethan": has_ethan,
        "ethan_count": ethan_count,
        "has_chain_hero": has_chain_hero,
        "has_obelith": has_obelith,
        "has_dark": has_dark,
        "nft_names": list(all_nft_names),
    }


# ─── Threshold evaluation ────────────────────────────────────

def evaluate_tier(holdings):
    """Evaluate on-chain tier from aggregated holdings."""
    pen = holdings["pen"]
    zor = holdings["zor"]

    # VIP3: 5M PEN OR Ethan NFT OR Obelith Setsuko
    if pen >= THRESHOLDS[3]["pen"] or holdings["has_ethan"] or holdings["has_obelith"]:
        return 3

    # VIP2: 1M PEN OR 50K ZOR OR Chain Hero NFT
    if pen >= THRESHOLDS[2]["pen"] or zor >= THRESHOLDS[2]["zor"] or holdings["has_chain_hero"]:
        return 2

    # VIP1: 200K PEN OR 10K ZOR OR any BCSH NFT
    if pen >= THRESHOLDS[1]["pen"] or zor >= THRESHOLDS[1]["zor"] or holdings["has_bcsh"]:
        return 1

    return 0


# ─── Progress calculation ────────────────────────────────────

def calc_progress(holdings, effective_tier):
    """Calculate progress toward next tier."""
    if effective_tier >= 3:
        return {
            "current_tier": TIER_NAMES[effective_tier],
            "next_tier": None,
            "message": "Maximum tier reached",
        }

    next_tier = effective_tier + 1
    next_name = TIER_NAMES[next_tier]
    result = {
        "current_tier": TIER_NAMES[effective_tier],
        "next_tier": next_name,
    }

    pen = holdings["pen"]
    zor = holdings["zor"]

    options = []
    if next_tier == 1:
        pen_needed = THRESHOLDS[1]["pen"] - pen
        zor_needed = THRESHOLDS[1]["zor"] - zor
        if pen_needed > 0:
            options.append(f"{pen_needed:,.0f} more PEN")
        if zor_needed > 0:
            options.append(f"{zor_needed:,.0f} more ZOR")
        if not holdings["has_bcsh"]:
            options.append("Any BCSH NFT")
    elif next_tier == 2:
        pen_needed = THRESHOLDS[2]["pen"] - pen
        zor_needed = THRESHOLDS[2]["zor"] - zor
        if pen_needed > 0:
            options.append(f"{pen_needed:,.0f} more PEN")
        if zor_needed > 0:
            options.append(f"{zor_needed:,.0f} more ZOR")
        if not holdings["has_chain_hero"]:
            options.append("Any Chain Hero NFT (Setsuko, Lazuli, Avyaan, Launch, Nomad, BCSH CORE)")
    elif next_tier == 3:
        pen_needed = THRESHOLDS[3]["pen"] - pen
        if pen_needed > 0:
            options.append(f"{pen_needed:,.0f} more PEN")
        if not holdings["has_ethan"]:
            options.append("Ethan NFT (Ethereum)")
        if not holdings["has_obelith"]:
            options.append("Obelith Setsuko")

    result["upgrade_options"] = options
    return result


# ─── Main resolve ─────────────────────────────────────────────

def resolve(wallet=None, username=None, discord_id=None):
    """
    Main entry point. Single source of truth.

    Returns flat dict with everything. No include= nonsense.
    """
    # 1. Find user
    user = lookup_user(wallet=wallet, username=username, discord_id=discord_id)
    if not user:
        return None

    user_id = user["id"]

    # 2. Source A: Discord role tier
    role_tier, discord_roles, sub_roles = get_discord_role_tier(user_id)

    # 3. Source B: On-chain tier
    wallets = get_all_wallets(user_id)
    holdings = collect_onchain_holdings(wallets) if wallets else {
        "pen": 0, "zor": 0, "pen_by_chain": {}, "bcsh_count": 0,
        "has_bcsh": False, "has_ethan": False, "ethan_count": 0,
        "has_chain_hero": False, "has_obelith": False, "has_dark": False,
        "nft_names": [],
    }
    chain_tier = evaluate_tier(holdings)

    # 4. Resolve: max wins
    effective_tier = max(role_tier, chain_tier)
    if role_tier > chain_tier:
        resolved_from = "discord_role"
    elif chain_tier > role_tier:
        resolved_from = "on_chain"
    else:
        resolved_from = "both_equal"

    # 5. Referral rate from the ONE authoritative dict
    rate = REFERRAL_RATES.get(effective_tier, 0)
    can_payout = effective_tier >= 2

    # 6. Build flat response — everything in one shot
    progress = calc_progress(holdings, effective_tier)

    return {
        # Tier resolution
        "effective_tier": effective_tier,
        "tier_name": TIER_NAMES.get(effective_tier, "Newcomer"),
        "on_chain_tier": chain_tier,
        "role_tier": role_tier,
        "resolved_from": resolved_from,

        # Identity
        "username": user.get("username"),
        "primary_wallet": user.get("mm_address"),
        "verified": user.get("verified", False),

        # Referral
        "referral_rate": rate,
        "referral_rate_display": f"{int(rate * 100)}%" if rate > 0 else "0%",
        "can_payout": can_payout,

        # Balances
        "pen_total": round(holdings["pen"], 2),
        "pen_by_chain": {k: round(v, 2) for k, v in holdings.get("pen_by_chain", {}).items()},
        "zor_total": round(holdings["zor"], 2),

        # NFTs
        "bcsh_count": holdings["bcsh_count"],
        "has_bcsh": holdings["has_bcsh"],
        "has_ethan": holdings["has_ethan"],
        "ethan_count": holdings.get("ethan_count", 0),
        "has_chain_hero": holdings["has_chain_hero"],
        "has_obelith": holdings["has_obelith"],
        "has_dark": holdings.get("has_dark", False),
        "nft_names": holdings["nft_names"],

        # Discord roles
        "discord_roles": discord_roles,
        "sub_roles": sub_roles,

        # Wallets
        "wallets": wallets,

        # Progress
        "progress": progress,
    }
