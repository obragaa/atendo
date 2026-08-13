-- 001_init.sql — Esquema inicial do Atendo.
--
-- Multi-tenancy com isolamento garantido pelo banco: além do WHERE tenant_id
-- em cada query, Row Level Security filtra as tabelas de dados de cliente.
-- O modo de falha mais provável de um SaaS multi-tenant não é invasão, é um
-- WHERE esquecido numa query nova meses depois. Com RLS, esse bug devolve
-- zero linhas em vez de dado de outro cliente.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Catálogo de tenants. A chave de API em claro nunca vai ao banco: apenas o
-- SHA-256, suficiente para autenticar e inútil para quem ler a tabela.
-- ---------------------------------------------------------------------------
CREATE TABLE tenants (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    api_key_hash TEXT NOT NULL UNIQUE,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Base de conhecimento (RAG).
-- UNIQUE (tenant_id, content_sha) é o que torna a ingestão idempotente:
-- ingerir o mesmo arquivo duas vezes não duplica chunks.
-- ---------------------------------------------------------------------------
CREATE TABLE documents (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    content_sha TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, content_sha)
);

CREATE TABLE chunks (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   VECTOR(1536) NOT NULL
);

CREATE INDEX idx_chunks_tenant ON chunks (tenant_id);
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Cache semântico: perguntas frequentes respondidas sem chamar o modelo.
-- Fica no Postgres porque exige busca por similaridade e o pgvector já está
-- no projeto; o rate limit volátil fica no Redis.
-- ---------------------------------------------------------------------------
CREATE TABLE semantic_cache (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    embedding  VECTOR(1536) NOT NULL,
    hits       INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cache_tenant_expira ON semantic_cache (tenant_id, expires_at);
CREATE INDEX idx_cache_embedding ON semantic_cache USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Contabilidade de custo: uma linha por chamada de modelo.
-- Esta tabela é a fonte do preço cobrado do cliente — o que permite
-- precificar a mensalidade com margem conhecida em vez de chute.
-- ---------------------------------------------------------------------------
CREATE TABLE usage_events (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id TEXT,
    model           TEXT NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(12, 6) NOT NULL DEFAULT 0,
    cached          BOOLEAN NOT NULL DEFAULT FALSE,
    escalated       BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_usage_tenant_data ON usage_events (tenant_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Conversas e mensagens (histórico por canal).
-- ---------------------------------------------------------------------------
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    channel     TEXT NOT NULL DEFAULT 'web',
    external_id TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_messages_conversa ON messages (conversation_id, created_at);

-- ---------------------------------------------------------------------------
-- Agendamentos e leads.
-- UNIQUE (tenant_id, starts_at) impede agendamento duplo por corrida: duas
-- pessoas confirmando o mesmo horário ao mesmo tempo — uma vence no banco,
-- a outra recebe "horário ocupado", sem lock explícito na aplicação.
-- ---------------------------------------------------------------------------
CREATE TABLE appointments (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    customer   TEXT NOT NULL,
    phone      TEXT,
    service    TEXT NOT NULL,
    starts_at  TIMESTAMPTZ NOT NULL,
    status     TEXT NOT NULL DEFAULT 'confirmado',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, starts_at)
);

CREATE TABLE leads (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name       TEXT,
    phone      TEXT,
    interest   TEXT NOT NULL,
    notes      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Row Level Security.
-- A aplicação define app.tenant_id por transação (SELECT set_config(..., TRUE))
-- e as policies filtram por ele. current_setting com missing_ok=TRUE devolve
-- NULL quando o contexto não foi definido — e NULL não casa com nada:
-- sem contexto, nenhuma linha.
-- ---------------------------------------------------------------------------
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON chunks
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

ALTER TABLE semantic_cache ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON semantic_cache
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON messages
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON appointments
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON leads
    USING (tenant_id = current_setting('app.tenant_id', TRUE));

-- ---------------------------------------------------------------------------
-- Role da aplicação. RLS não se aplica a superusuário: se a API conectasse
-- como postgres, as policies seriam decorativas. A aplicação conecta como
-- atendo_app, que enxerga apenas o que as policies liberam.
-- (Senha de demo; em produção, vem do gerenciador de segredos.)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'atendo_app') THEN
        CREATE ROLE atendo_app LOGIN PASSWORD 'atendo_app';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO atendo_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO atendo_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO atendo_app;
