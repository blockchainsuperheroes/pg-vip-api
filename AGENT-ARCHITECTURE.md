# Pentagon AI Agent — Access Architecture

> Internal documentation for the agent access model, security layers,
> and service scope. This defines what an AI agent CAN and CANNOT do
> when operating on behalf of a Pentagon user.

**Version:** 1.0
**Date:** 2026-05-30
**Authors:** Cerise01, nftprof
**Status:** Production (Phase 1)

---

## 1. Overview

Pentagon AI agents serve as personal concierges for VIP/NFC cardholders.
Each agent operates within a strict security boundary: it can access
data and perform actions ONLY for the specific user it's bound to,
through a scoped API key, with a signing keeper that never exposes
private keys.

The access model has three layers:

```
┌─────────────────────────────────────────────────────┐
│  Layer 1: User Authentication                        │
│  User proves identity → JWT session                  │
│  (id.peg.gg login, Pentagon Games account)           │
├─────────────────────────────────────────────────────┤
│  Layer 2: Agent Authorization                        │
│  Per-VIP API key (pgvip_*) grants scoped access      │
│  Agent reads user data, proposes actions              │
├─────────────────────────────────────────────────────┤
│  Layer 3: Signing Keeper                             │
│  VIP API server decrypts key, signs, returns receipt │
│  Private key never leaves server memory              │
└─────────────────────────────────────────────────────┘
```

---

## 2. Access Patterns: Agent vs App vs User

### 2.1 Current App Key Access (PG_APP_KEY)

The existing `PG_APP_KEY` / `API_KEY_SECRET` is a service-level key
used by internal apps (role bot, service backend). It provides broad
access across all users:

| Capability | App Key |
|-----------|---------|
| Read ANY user by discord_id | ✅ `/user/info_by_discord/{id}` |
| Read ANY user private info | ✅ `/user/info_private` |
| Read ANY user's wallet | ✅ via DB queries |
| Write to ANY user's data | ✅ (used by role bot) |
| Cross-user queries | ✅ No scoping |

**Risk:** A compromised app key exposes ALL users.

### 2.2 Agent VIP Key Access (pgvip_*)

The agent VIP key is scoped to a SINGLE user:

| Capability | Agent Key |
|-----------|-----------|
| Read bound user's VIP status | ✅ `/user/vip_status` (auto-scoped) |
| Read bound user's wallet balance | ✅ `/agent/wallet/info` |
| Read bound user's profile | ✅ `/agent/user/profile` |
| Propose transactions | ✅ `/agent/wallet/propose` |
| Execute confirmed proposals | ✅ `/agent/wallet/execute/{id}` |
| Read OTHER users' data | ❌ DB enforces `WHERE user_id = $bound` |
| See private key | ❌ Never returned by any endpoint |
| Sign without user confirmation | ❌ Requires confirmed proposal |
| Access app-key endpoints | ❌ Different auth mechanism |

**Risk:** A compromised agent key exposes ONE user only.

### 2.3 User Direct Access (JWT)

When a user is logged in on id.peg.gg:

| Capability | User JWT |
|-----------|----------|
| Read own profile, balances | ✅ via authenticated endpoints |
| Confirm/reject agent proposals | ✅ `/agent/wallet/proposal/{id}/confirm` |
| See private key | ❌ Never returned |
| Access other users' data | ❌ JWT scoped to self |
| Call agent-only endpoints | ❌ Requires VIP key, not JWT |

### 2.4 Agent Public Data Access

Agents CAN access public information about other users that the
user themselves might not know is available:

| Public Data | Agent Access | Source |
|------------|-------------|--------|
| Other user's VIP tier | �� Public endpoint | `/user/vip_status?username=X` |
| Other user's PEN/ZOR balance | ✅ On-chain, public | RPC / VIP API |
| Other user's NFT holdings | ✅ On-chain, public | BCSH API |
| Other user's Discord roles | ✅ Public data | VIP API response |
| Other user's email | ❌ Private | Not exposed |
| Other user's wallet key | ❌ Private | Never exposed |
| Other user's linked wallets | ❌ Private | Requires auth |

This is a feature, not a bug. The agent can help the user understand
the ecosystem ("drakasin1 is VIP3 with 15 BCSH NFTs") using publicly
available on-chain data, similar to how anyone can look up a wallet
on a block explorer.

---

## 3. Service Catalogue — Agent Access Matrix

All services running on pg-identity-be (13.212.154.41):

| Service | Port | Agent Access | Scope | Notes |
|---------|------|-------------|-------|-------|
| **pg-vip-api** | 9022 | ✅ Full (via VIP key) | Per-user | Agent's primary API |
| **pentagon-login-backend** | 8031 | ❌ No direct access | — | User auth only |
| **pen-wallet-backend** | 8031 | ❌ No direct access | — | Internal wallet ops |
| **pentagon-service-backend** | varies | ❌ No direct access | — | Token balances (called by VIP API internally) |
| **pentagon-id-api** | 3456 | ✅ Chat relay only | Per-session | Chat send/poll/bind |
| **pentagon-id-chat** | 4567 | ✅ Chat relay only | Per-session | SSE + Discord threads |
| **discord-role-assigner-bot** | — | ❌ No access | — | Internal bot |
| **email-relay** | — | ❌ No access | — | Internal |
| **api-peg-gg** | varies | ❌ No access (future) | — | PEG.GG storage |
| **pentagon-backend** | varies | ❌ No access | — | Legacy |
| **pentagon-celery** | — | ❌ No access | — | Background tasks |

### What the agent accesses THROUGH pg-vip-api:

The VIP API is a controlled gateway. It internally calls other services
but the agent only sees the VIP API's filtered responses:

```
Agent (VIP key) → pg-vip-api
                    ├→ pg_identity_db (user lookup, wallet address)
                    ├→ pentagon-service-backend (PEN/ZOR balances)
                    ├→ api.bcsh.xyz (NFT holdings)
                    ├→ Pentagon Chain RPC (on-chain balances, signing)
                    └→ Ethereum RPC (ETH PEN balance fallback)
```

The agent never calls these backend services directly.

---

## 4. Security Architecture

### 4.1 Keeper Model

The VIP API acts as a "Signing Keeper." The agent sends instructions,
the keeper executes:

```
Agent: "Send 10 PC to 0x123" (proposal)
  → Keeper validates VIP key (scoped to user)
  → Keeper validates proposal is user-confirmed
  → Keeper decrypts private key (in RAM only)
  → Keeper signs transaction
  → Keeper broadcasts to Pentagon Chain
  → Keeper wipes key from memory
  → Keeper returns: { tx_hash, explorer_url }
```

### 4.2 Response Scrubbing

Every JSON response from the VIP API passes through a scrubbing
middleware that blocks responses containing:
- `0x` + 64 hex chars (private key format)
- `"key": "..."` (keystore fragments)
- `"privateKey"`, `"private_key"`, `"secret"` fields

If detected, the response is replaced with an error and a
KEEPER VIOLATION is logged.

### 4.3 Cross-User Isolation

```sql
-- Every agent query includes this filter:
WHERE user_id = $bound_user_id  -- from VIP key lookup
```

The VIP key is bound to a `user_id` at creation time. The binding
is in the `vip_api_keys` table and enforced at every query.
There is no API parameter that can override this binding.

### 4.4 Proposal Flow (Human-in-the-Loop)

```
1. Agent proposes → status: "pending"
2. User confirms (via card page or Discord) → status: "confirmed"
3. Agent executes → status: "executed", tx_hash returned
4. Proposal expires after 24h if not confirmed
```

No transaction can execute without step 2. This is not behavioral
("the agent decides not to") — it's structural (the code physically
requires a confirmed proposal_id).

---

## 5. Agent Identity & Channel Architecture

### 5.1 Agent Roles

| Agent | Role | Access Level |
|-------|------|-------------|
| **Emiko02** | Public-facing VIP concierge | Per-VIP API keys, no credentials |
| **Emiko01** | Internal coordinator | Full internal access, guides Emiko02 |
| **Cerise01** | Dev/ops agent, nftprof's personal agent | Full access, builds infrastructure |
| **Cerise02** | Dev support | Similar to Cerise01 |

### 5.2 Channel Architecture

Per-user channel on Pentagon Chain Info server (1297755604907069501):

```
#agent-{username} (private)
  ├── Main channel: owner ↔ agent private conversation
  ├── Visitor threads: each guest gets isolated thread
  │     └── Thread auto-archives after 7 days
  └── Permissions: owner + Emiko02 + Emiko01 + Cerise01 only
```

Access points:
1. **Web** (id.peg.gg/card/{username}): Chat widget relays to Discord thread
2. **Discord**: Owner accesses their channel directly

### 5.3 Session Types

| Session Type | Notification | Agent Behavior |
|-------------|-------------|----------------|
| Guest (anonymous) | 🔔 New visitor | Public info only, polite redirect |
| Guest (logged in, not owner) | 🔔 New visitor (authenticated) | Their own public profile data |
| Owner (logged in as card holder) | 🏠 Owner logged in | Full VIP API access, wallet ops, account management |

---

## 6. API Endpoint Reference

### Agent Endpoints (require X-VIP-Agent-Key)

| Method | Path | Scope | Description |
|--------|------|-------|-------------|
| GET | `/user/vip_status` | read | Auto-scoped VIP tier, balances, NFTs |
| GET | `/agent/wallet/info` | wallet | Internal wallet address + balances |
| GET | `/agent/user/profile` | read | Username, avatar, socials, wallets |
| POST | `/agent/wallet/propose` | wallet | Propose a transaction |
| GET | `/agent/wallet/proposal/{id}` | wallet | Check proposal status |
| POST | `/agent/wallet/execute/{id}` | wallet | Execute confirmed proposal |

### User Endpoints (require user JWT)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/agent/wallet/proposal/{id}/confirm` | Confirm a pending proposal |
| POST | `/agent/wallet/proposal/{id}/reject` | Reject a pending proposal |

### Admin Endpoints (require X-Admin-Key)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/agent-keys/generate` | Create per-VIP API key |
| GET | `/admin/agent-keys/list` | List active keys (no values) |
| POST | `/admin/agent-keys/revoke/{id}` | Revoke a key |

### Public Endpoints (no auth)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/user/vip_status?username=X` | Public VIP tier lookup |
| GET | `/health` | Service health check |

---

## 7. Database Tables

### vip_api_keys
Binds agent API keys to specific users. One key per user per agent.

| Column | Type | Purpose |
|--------|------|---------|
| key_hash | varchar(128) | bcrypt hash (key never stored plain) |
| key_prefix | varchar(16) | First chars for index lookup |
| user_id | integer FK | Bound user (enforced on every query) |
| agent_id | varchar(100) | Which agent (e.g., "emiko02") |
| scopes | jsonb | ["read", "wallet"] |
| chain | varchar(20) | "pentagon" (default) |

### agent_wallet_proposals
Transaction proposals requiring user confirmation.

| Column | Type | Purpose |
|--------|------|---------|
| proposal_id | varchar(64) | Unique proposal identifier |
| api_key_id | integer FK | Which agent key created it |
| user_id | integer FK | Bound user |
| status | varchar(20) | pending/confirmed/rejected/expired/executed |
| tx_hash | varchar(100) | Filled after execution |

### agent_wallet_audit
Complete audit trail of all agent operations.

| Column | Type | Purpose |
|--------|------|---------|
| action | varchar(50) | What happened |
| details | jsonb | Full context |
| ip_address | varchar(50) | Request origin |

---

## 8. Future Roadmap

### Phase 2: Expanded Agent Capabilities
- [ ] Agent can read user's payment history
- [ ] Agent can update user's privacy settings (with confirmation)
- [ ] Agent can manage user's connected socials
- [ ] Agent can access user's referral data and payouts

### Phase 3: Pentagon AI Orchestration Core
- [ ] Full owner/guest session split (Pentagon AI Design §4)
- [ ] Tiered model routing (Haiku/Sonnet/Opus per session type)
- [ ] $PC metering for agent operations
- [ ] AgentCert L1 gating for wallet operations
- [ ] ERC-8170 sovereign agent identity

### Phase 4: Multi-Chain + DeFi
- [ ] Multichain wallet ops (ETH, Arbitrum — opt-in)
- [ ] DeFi simulation and training
- [ ] Cross-chain bridge operations (with confirmation)

---

## 9. Credentials Reference (Locations Only)

| Credential | Location | Who Has Access |
|-----------|----------|---------------|
| VIP API keys (pgvip_*) | ~/clawd-persist/SECRETS.md | Agent servers only |
| Admin key | Server .env + SECRETS.md | Cerise01 only |
| WALLET_PASSWORD | Server .env | VIP API service only |
| User JWTs | Browser session | User only |
| PG_APP_KEY | Server settings | Internal services only |

**No credentials are stored in this document.**

---

*This document is the source of truth for agent access patterns.
Update it when capabilities change.*
