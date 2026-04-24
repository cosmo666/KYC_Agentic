-- Runs once, on first boot, as the POSTGRES_USER superuser in postgres:16-alpine.
-- The "kyc" DB is already created by the POSTGRES_DB env var; we just ensure the
-- uuid-ossp extension exists inside it.

\connect kyc
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
