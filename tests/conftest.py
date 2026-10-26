import os

# Tests must never load production credentials or contact production databases.
os.environ.update({
    "BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
    "BOTOHUB_TOKEN": "test-integration-token",
    "ADMIN_IDS": "964164519,1254138354",
    "DB_USER": "test", "DB_PASSWORD": "test", "DB_NAME": "test",
    "DB_HOST": "localhost", "DB_PORT": "5432",
    "DB_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
})
