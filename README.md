# pg-vip-api

Unified VIP tier resolution API for Pentagon Games.

Single endpoint replaces the old 3-API client-side pattern (`api.account` + `api.service` + `api.bcsh.xyz`) with one `GET /user/vip_status` call. Backend owns all tier logic. No more `Math.max` across three APIs on the frontend.

## Live Endpoints

**User VIP lookup:**
```
https://api.account.pentagon.games/user/vip_status
```

**VIP tier stats (total counts):**
```
https://api.account.pentagon.games/stats
```

Hosted on pg-identity-be (AWS `13.212.154.41`), port 9022, proxied through nginx alongside the identity API.

## Authentication

**Currently public** (v1.3). No API key required for reads.

The endpoint previously accepted `X-VIP-API-Key` or `X-PG-App-Key` headers. Auth check is now a no-op but headers are still accepted for backward compatibility.

## Query Parameters

Provide at least one identifier:

| Param | Type | Description |
|-------|------|-------------|
| `wallet` | string | EVM address (0x...) |
| `username` | string | Pentagon Games username |
| `discord_id` | string | Discord user snowflake ID |

Multiple params can be combined. The resolver tries them in order: wallet, username, discord_id.

## Example Requests

**Get user VIP status:**
```bash
curl "https://api.account.pentagon.games/user/vip_status?username=nftprof"
```

**Get VIP tier stats:**
```bash
curl "https://api.account.pentagon.games/stats"
```

## Response Formats

### `/user/vip_status` Response

```json
{
  "status": true,
  "result": {
    "effective_tier": 3,
    "tier_name": "VIP3",
    "on_chain_tier": 3,
    "role_tier": 2,
    "resolved_from": "on_chain",

    "username": "nftprof",
    "primary_wallet": "0x...",
    "verified": true,

    "referral_rate": 0.15,
    "referral_rate_display": "15%",
    "can_payout": true,

    "pen_total": 11942834.39,
    "pen_by_chain": {
      "ethereum": 11741190.78,
      "pentagon": 201643.61,
      "arbitrum": 0.0
    },
    "zor_total": 52000.0,

    "bcsh_count": 12,
    "has_bcsh": true,
    "has_ethan": false,
    "ethan_count": 0,
    "has_chain_hero": true,
    "has_obelith": true,
    "has_dark": true,
    "nft_names": ["Nomad", "Dark Setsuko", "Obelith Setsuko", "BCSH CORE", "Lazuli"],

    "discord_roles": ["VIP2", "BCSH Holder", "PG User"],
    "sub_roles": ["200K PEN", "1M PEN", "BCSH", "Chain Hero"],

    "wallets": ["0xabc...", "0xdef..."],

    "progress": {
      "current_tier": "VIP3",
      "next_tier": null,
      "message": "Maximum tier reached"
    }
  }
}
```

### `/stats` Response

Returns total VIP member counts from `user_discord_roles` table. Does not require authentication.

```json
{
  "vip1": 44,
  "vip2": 27,
  "vip3": 10,
  "total": 81,
  "timestamp": "2026-06-01T18:06:06.615495+00:00"
}
```

**Notes:**
- Counts users by their **highest tier** (VIP3 > VIP2 > VIP1)
- Data comes from most recent role sync per user
- Updated in real-time (no caching)
- Use for analytics, dashboards, or loyalty calculations

## Response Fields

### Tier Resolution
| Field | Type | Description |
|-------|------|-------------|
| `effective_tier` | int | Final tier (0-3). `max(on_chain_tier, role_tier)` |
| `tier_name` | string | Human-readable: Newcomer, VIP1, VIP2, VIP3 |
| `on_chain_tier` | int | Tier from on-chain holdings (Source B) |
| `role_tier` | int | Tier from Discord role sync (Source A) |
| `resolved_from` | string | Which source won: `on_chain`, `discord_role`, or `both_equal` |

### Identity
| Field | Type | Description |
|-------|------|-------------|
| `username` | string | PG username |
| `primary_wallet` | string | Primary linked wallet |
| `verified` | bool | Account email verified |

### Referral
| Field | Type | Description |
|-------|------|-------------|
| `referral_rate` | float | Decimal rate (0.05 = 5%) |
| `referral_rate_display` | string | Human-readable ("5%") |
| `can_payout` | bool | True if VIP2+ (eligible for referral payouts) |

### Balances
| Field | Type | Description |
|-------|------|-------------|
| `pen_total` | float | Total PEN across all chains and wallets |
| `pen_by_chain` | object | Breakdown: `ethereum`, `pentagon`, `arbitrum` |
| `zor_total` | float | Total ZOR balance |

### NFTs
| Field | Type | Description |
|-------|------|-------------|
| `bcsh_count` | int | Total BCSH NFTs owned |
| `has_bcsh` | bool | Owns any BCSH NFT |
| `has_ethan` | bool | Owns Ethan NFT (Ethereum mainnet) |
| `ethan_count` | int | Number of Ethan NFTs |
| `has_chain_hero` | bool | Owns a Chain Hero NFT |
| `has_obelith` | bool | Owns Obelith Setsuko (on-chain tier 2) |
| `has_dark` | bool | Owns Dark Setsuko (on-chain tier 1) |
| `nft_names` | array | List of unique NFT collection names |

### Discord
| Field | Type | Description |
|-------|------|-------------|
| `discord_roles` | array | Discord VIP roles from last bot sync |
| `sub_roles` | array | Sub-roles (200K PEN, BCSH, Chain Hero, etc.) |

### Wallets
| Field | Type | Description |
|-------|------|-------------|
| `wallets` | array | All bound EVM wallet addresses |

### Progress
| Field | Type | Description |
|-------|------|-------------|
| `progress.current_tier` | string | Current tier name |
| `progress.next_tier` | string or null | Next tier name, null if max |
| `progress.upgrade_options` | array | What the user needs for the next tier |

## Discord Role System (Sentinel Bot)

The **Sentinel** bot manages Discord role assignment for the Pentagon Games public server (`932412707209109544`). It runs on pg-identity-be alongside the VIP API and syncs roles based on PG Identity account data, on-chain holdings, and connected socials.

**Bot location:** `/var/www/bots/discord-role-assigner-bot/` on pg-identity-be (AWS `13.212.154.41`)

### Main Roles (8 total)

These are the primary Discord roles assigned by Sentinel:

| Role | Requirement | Description |
|------|-------------|-------------|
| **Newcomer** | No PG account or no qualifications | Default role. Removed once any real role is earned. |
| **PG User** | `mm_address` exists on PG Identity | User has a Pentagon Games account with a wallet (generated or linked). |
| **Web3 User** | `metamask_bind = True` | User connected an external EOA wallet (MetaMask, etc.) to their PG account. Not just the auto-generated wallet. |
| **Social Proof** | `twitter_username` AND `telegram_username` present | User linked both Twitter and Telegram. Discord is implied (they're on the server). |
| **BCSH Holder** | BCSH NFT count > 0 | Owns at least 1 BCSH collection NFT (aggregated across all connected wallets). |
| **VIP1** | 10K+ ZOR **or** 200K+ PEN **or** any BCSH NFT | Entry-level VIP tier. |
| **VIP2** | 50K+ ZOR **or** 1M+ PEN **or** Chain Hero NFT | Mid-tier VIP. |
| **VIP3** | 5M+ PEN **or** Ethan NFT **or** Obelith Setsuko | Top-tier VIP. |

### Sub-Roles (9 total)

Badge/achievement roles showing what specifically qualifies a user. These are tracked in the `user_discord_roles` table alongside main roles.

**Token Balance Badges:**

| Sub-Role | Requirement |
|----------|-------------|
| **10K ZOR** | Holds 10,000+ ZOR |
| **50K ZOR** | Holds 50,000+ ZOR |
| **200K PEN** | Holds 200,000+ PEN (ETH + Arbitrum + Pentagon Chain combined) |
| **1M PEN** | Holds 1,000,000+ PEN |
| **5M PEN** | Holds 5,000,000+ PEN |

**NFT Badges:**

| Sub-Role | Requirement |
|----------|-------------|
| **BCSH** | Owns any BCSH collection NFT |
| **Ethan** | Owns an Ethan NFT (Ethereum mainnet) |
| **Chain Hero** | Owns any Chain Hero NFT (Setsuko, Lazuli, Avyaan, Launch, Nomad, or BCSH CORE) |
| **Obelith** | Owns an Obelith Setsuko (on-chain `tokenTier() == 2` on Pentagon Chain) |

### Role Assignment Flow

1. User clicks the **"Verify Identity"** button in the `#get-roles` channel
2. Sentinel calls PG Identity API (`/user/info_by_discord/{discord_id}`) to fetch account data
3. Checks `mm_address`, `metamask_bind`, `twitter_username`, `telegram_username` for base roles
4. If wallets exist, aggregates balances and NFTs across ALL connected wallets (primary + external MetaMask)
5. Computes VIP tier from token balances and NFT holdings
6. Assigns/removes roles accordingly
7. Stores role state to `user_discord_roles` table via PG Identity API

### Mechanics

| Mechanic | Detail |
|----------|--------|
| **Verify cooldown** | 4 hours between manual verify button clicks |
| **Periodic audit** | Every 4 hours, bot re-checks all role holders and removes roles if they no longer qualify |
| **Tier regain cooldown** | Currently **disabled** (was 7-day lockout, turned off during ETH→PC bridge migration) |
| **Multi-wallet aggregation** | Balances summed across ALL connected wallets (primary `mm_address` + all external MetaMask wallets) |
| **Safe removal** | If any API call fails during periodic check, user is skipped entirely (never downgraded on incomplete data) |
| **Newcomer cleanup** | Newcomer role is automatically removed when any real role is granted |

### Data Sources

| Data | Source | Notes |
|------|--------|-------|
| User identity + wallets | PG Identity API (`api.account.pentagon.games`) | Primary wallet + external wallets from `user_external_wallets` |
| PEN balance | Service API (`api.service.pentagon.games`) + Pentagon Chain RPC | ETH + Arbitrum via Service API, Pentagon Chain via direct `balanceOf` |
| ZOR balance | Service API (`api.service.pentagon.games`) | |
| BCSH NFTs | `api.bcsh.xyz/user/nfts` | Paginated, Pentagon Chain |
| Setsuko tier | Pentagon Chain RPC | `tokenTier()` on Setsuko Distributor (`0xeC18CcC474C0CB470D947bE03a107989B980AD31`) |
| Social accounts | PG Identity `extra_data` | `twitter_username`, `telegram_username` |

### Slash Commands

| Command | Permission | Description |
|---------|------------|-------------|
| `/setup` | Admin only | Posts the Sentinel verify embed with button in the current channel |
| `/audit` | Admin only | Runs a full role audit on all server members |

## VIP Tier Thresholds

| Tier | Token Requirement | NFT Requirement | Referral Rate |
|------|-------------------|-----------------|---------------|
| **VIP1** | 200K PEN or 10K ZOR | Any BCSH NFT | 0% (display only) |
| **VIP2** | 1M PEN or 50K ZOR | Chain Hero NFT | 5% |
| **VIP3** | 5M PEN | Ethan (ETH) or Obelith Setsuko | 15% |

Token OR NFT qualifies. Whichever gives the higher tier wins.

**Chain Hero NFTs:** Setsuko, Dark Setsuko, Obelith Setsuko, Lazuli, Avyaan, Launch, Nomad, BCSH CORE

**Setsuko tiers (on-chain):**
- Normal Setsuko = Chain Hero (VIP2 path)
- Dark Setsuko (tier 1) = Chain Hero (VIP2 path)
- Obelith Setsuko (tier 2) = VIP3 path

> **Note:** The BCSH API returns variant names ("Dark Setsuko", "Obelith Setsuko") rather than plain "Setsuko". The resolver uses substring matching to detect all Setsuko variants, then calls `tokenTier()` on-chain with the full token ID (including `5555` chain prefix) to determine the exact tier.

## Architecture

```
Consumer
  │
  GET /user/vip_status?wallet=0x...
  │
  ▼
pg-vip-api (port 9022, gunicorn)
  │
  ├─ [1] User Lookup
  │     └─ pg_identity_db (AWS RDS 172.31.x.x:5432)
  │        Query by wallet / username / discord_id
  │        Get all bound wallets from user_external_wallets
  │
  ├─ [2] Source A: Discord Role Tier
  │     └─ user_discord_roles table (synced by role bot every 4h)
  │        Maps VIP1/VIP2/VIP3 roles → tier int
  │
  ├─ [3] Source B: On-Chain Holdings (per wallet)
  │     ├─ PEN balance
  │     │   ├─ Service API (api.service.pentagon.games) → ETH + ARB
  │     │   ├─ Web3 fallback → balanceOf on ETH mainnet (0x5ee3...8f66)
  │     │   └─ Direct RPC → balanceOf on Pentagon Chain (0x02fa...8721)
  │     │
  │     ├─ ZOR balance
  │     │   └─ Service API (api.service.pentagon.games)
  │     │
  │     ├─ BCSH NFTs
  │     │   └─ api.bcsh.xyz/user/nfts (paginated, Pentagon Chain)
  │     │
  │     ├─ Ethan NFTs
  │     │   └─ api.bcsh.xyz/user/nfts?chain_id=1 (Ethereum)
  │     │
  │     └─ Setsuko on-chain tier
  │         └─ tokenTier() on Setsuko Distributor contract (Pentagon RPC)
  │
  └─ [4] Resolve
        effective_tier = max(role_tier, chain_tier)
        Return flat JSON with everything
```

### Web3 Fallback

The Service API (`api.service.pentagon.games`) for PEN balance is occasionally flaky, returning 0 for wallets that have millions of PEN. When the Service API returns 0 for Ethereum PEN, the resolver falls back to a direct `balanceOf` call on the PEN ERC-20 contract on Ethereum mainnet via public RPC. This prevents false tier downgrades during upstream API hiccups.

## Error Responses

```json
// Missing params
{ "status": false, "error": "Provide at least one: wallet, username, or discord_id" }
// 422

// User not found
{ "status": false, "error": "User not found" }
// 404

// Internal error
{ "status": false, "error": "Internal error during tier resolution" }
// 500
```

## Health Check

```
GET /health
→ { "status": "ok", "service": "pg-vip-api" }
```

## Deployment

### Infrastructure
- **Server:** pg-identity-be (AWS `13.212.154.41`)
- **Process:** supervisor-managed, 2 gunicorn workers
- **Port:** 9022 (internal), proxied via nginx on 443
- **Database:** pg_identity_db on AWS RDS (private subnet)
- **Python:** 3.x with Flask

### Deploy Script

```bash
./deploy.sh
```

Syncs code via rsync, sets up virtualenv, installs deps, copies supervisor config, restarts service.

### Environment Variables

Copy `.env.example` to `.env` on the server and fill in credentials:

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_HOST` | PostgreSQL host | `172.31.46.190` |
| `DB_PORT` | PostgreSQL port | `5432` |
| `DB_NAME` | Database name | `pg_identity_db` |
| `DB_USER` | Database user | `backend_pg_account` |
| `DB_PASSWORD` | Database password | (required) |
| `SERVICE_API_KEY` | Key for api.service.pentagon.games | (required) |
| `PG_API_KEY` | Pentagon Games API key | (optional) |
| `PENTAGON_RPC` | Pentagon Chain RPC URL | `https://rpc.pentagon.games` |
| `ETH_RPC` | Ethereum mainnet RPC | `https://eth.drpc.org` |
| `PORT` | Server port | `9022` |
| `VIP_API_KEY` | API key for this service (legacy) | (optional) |

### Nginx

Routes `/user/vip_status` and `/user/vip` to port 9022 on the HTTPS server block for `api.account.pentagon.games`. All other routes continue to the identity backend on port 8031.

### Supervisor Config

```ini
[program:pg-vip-api]
command=/var/www/services/pg-vip-api/venv/bin/gunicorn -w 2 -b 0.0.0.0:9022 --timeout 60 app:app
directory=/var/www/services/pg-vip-api
autostart=true
autorestart=true
stderr_logfile=/var/log/pg-vip-api.err.log
stdout_logfile=/var/log/pg-vip-api.out.log
```

## Dependencies

```
flask==3.1.1
gunicorn==23.0.0
httpx==0.28.1
python-dotenv==1.1.0
psycopg2-binary==2.9.10
web3==7.12.0
```

## Version History

| Version | Changes |
|---------|---------|
| v1.5 | Added complete Discord Role System (Sentinel Bot) documentation: all 8 main roles, 9 sub-roles, assignment flow, mechanics, data sources |
| v1.4 | Fixed Setsuko tier detection: substring name matching + full token ID for `tokenTier()` |
| v1.3 | Made endpoint public, no auth required |
| v1.2 | Web3 fallback for ETH PEN balance when Service API flakes |
| v1.1 | Renamed to `/user/vip_status`, flattened response, removed `include=` param |
| v1.0 | Initial release, unified VIP tier resolution |

## Integration Notes

**For the Discord role bot:** Call `/user/vip_status?discord_id=X`, read `effective_tier`, assign matching Discord role. All threshold logic lives here, not in the bot.

**For frontend VIP pages:** Call with `wallet` or `username`. The `progress` field gives upgrade paths. `referral_rate_display` is ready to show.

**Multi-wallet:** Users with multiple bound wallets get aggregated balances across all wallets. PEN on Ethereum + Pentagon Chain + Arbitrum are summed per wallet, then totaled.
