import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Database
    DB_HOST = os.getenv("DB_HOST", "172.31.46.190")
    DB_PORT = int(os.getenv("DB_PORT", 5432))
    DB_NAME = os.getenv("DB_NAME", "pg_identity_db")
    DB_USER = os.getenv("DB_USER", "backend_pg_account")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # External APIs
    ACCOUNT_API_URL = os.getenv("ACCOUNT_API_URL", "https://api.account.pentagon.games")
    SERVICE_API_URL = os.getenv("SERVICE_API_URL", "https://api.service.pentagon.games")
    BCSH_API_URL = os.getenv("BCSH_API_URL", "https://api.bcsh.xyz")

    # API Keys
    SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
    PG_API_KEY = os.getenv("PG_API_KEY", "")

    # Pentagon Chain
    PENTAGON_RPC = os.getenv("PENTAGON_RPC", "https://rpc.pentagon.games")
    PEN_PC_CONTRACT = "0x02fa6e744C68B02F694fD29ECA7B4929718a8721"
    SETSUKO_DISTRIBUTOR = "0xeC18CcC474C0CB470D947bE03a107989B980AD31"

    # Ethereum mainnet (web3 fallback for PEN balance)
    ETH_RPC = os.getenv("ETH_RPC", "https://eth.drpc.org")
    PEN_ETH_CONTRACT = "0x5ee3188a3f8adee1d736edd4ae85000105c88f66"

    # Server
    PORT = int(os.getenv("PORT", 9022))
    HOST = os.getenv("HOST", "0.0.0.0")

    # Auth for callers of this service
    VIP_API_KEY = os.getenv("VIP_API_KEY", "")

    # HTTP client timeout
    HTTP_TIMEOUT = 15
