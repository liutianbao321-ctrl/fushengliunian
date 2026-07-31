CREATE EXTENSION IF NOT EXISTS vector;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fushengliunian_app') THEN
        CREATE ROLE fushengliunian_app LOGIN PASSWORD 'change-me-in-production';
    END IF;
END
$$;

GRANT USAGE, CREATE ON SCHEMA public TO fushengliunian_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fushengliunian_app;

-- 业务表由 FastAPI 启动时的 SQLAlchemy metadata 自动创建。
