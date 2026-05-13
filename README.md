# pg-vip-api

Unified VIP tier resolution endpoint for Pentagon Games.

Replaces the 3-API client-side pattern (`api.account` + `api.service` + `api.bcsh.xyz`) with one `GET /user/vip` call that backend owns entirely.

## Quick Start

```bash
# Local
cp .env.example .env
# Edit .env with real credentials
pip install -r requirements.txt
python app.py

# Deploy to pg-identity-be
./deploy.sh
```

## Endpoint

```
GET /user/vip_status?wallet=0x...
```

**Auth:** `X-VIP-API-Key` or `X-PG-App-Key` header

**Params:**
- `wallet` — EVM address
- `username` — PG username
- `discord_id` — Discord snowflake ID

No `include=` param. Returns everything flat in one shot.

**Response:**
```json
{
  "status": true,
  "result": {
    "effective_tier": 2,
    "tier_name": "VIP2",
    "on_chain_tier": 2,
    "role_tier": 1,
    "resolved_from": "on_chain",
    "username": "nftprof",
    "primary_wallet": "0x...",
    "verified": true,
    "referral_rate": 0.05,
    "referral_rate_display": "5%",
    "can_payout": true,
    "pen_total": 1200000.0,
    "zor_total": 52000.0,
    "bcsh_count": 3,
    "has_bcsh": true,
    "has_ethan": false,
    "has_chain_hero": true,
    "has_obelith": false,
    "discord_roles": ["VIP1", "BCSH Holder", "PG User"],
    "sub_roles": ["200K PEN", "1M PEN", "BCSH", "Chain Hero"],
    "wallets": ["0x..."],
    "progress": { "current_tier": "VIP2", "next_tier": "VIP3", "upgrade_options": ["3,800,000 more PEN"] }
  }
}
```

## Architecture

```
Consumer → GET /user/vip → pg-vip-api
                              ├─ DB: user_discord_roles (Source A)
                              ├─ Service API: PEN + ZOR balances (Source B)
                              ├─ BCSH API: NFT ownership (Source B)
                              ├─ Pentagon RPC: PEN on-chain + Setsuko tier (Source B)
                              └─ effectiveTier = max(Source_A, Source_B)
```

## VIP Tiers

| Tier | Token | NFT | Referral |
|------|-------|-----|----------|
| VIP1 | 200K PEN or 10K ZOR | Any BCSH NFT | 0% (display only) |
| VIP2 | 1M PEN or 50K ZOR | Chain Hero (Setsuko/Lazuli/Avyaan/Launch/Nomad/BCSH CORE) | 5% |
| VIP3 | 5M PEN | Ethan (ETH) or Obelith Setsuko | 15% |

## Deploy

Runs on pg-identity-be (`13.212.154.41`) via supervisor on port 9022.
