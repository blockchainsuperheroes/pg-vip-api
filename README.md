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
GET /user/vip?wallet=0x...&include=balances,nfts,roles,wallets,progress
```

**Auth:** `X-VIP-API-Key` or `X-PG-App-Key` header

**Params:**
- `wallet` — EVM address
- `username` — PG username
- `discord_id` — Discord snowflake ID
- `include` — comma-separated: `balances`, `nfts`, `roles`, `wallets`, `progress`

**Response:**
```json
{
  "status": true,
  "result": {
    "tier": {
      "level": 2,
      "name": "VIP2",
      "resolved_from": "on_chain",
      "sources": {
        "discord_role_tier": 1,
        "on_chain_tier": 2,
        "effective_tier": 2
      }
    },
    "identity": { "username": "nftprof", "primary_wallet": "0x...", "verified": true },
    "referral": { "rate": 0.05, "rate_display": "5%", "can_payout": true }
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
