-- ============================================================
-- Enterprise Multi-Agent Orchestration Platform
-- PostgreSQL Schema: Task State, Agent Status, Data Payload
-- ============================================================

-- Enum types for strict state transitions
CREATE TYPE task_status AS ENUM (
    'PENDING',        -- created, not yet decomposed
    'DECOMPOSING',    -- orchestrator is splitting into subtasks
    'DISPATCHED',     -- all subtasks published to event bus
    'IN_PROGRESS',    -- at least one subtask running
    'AWAITING_DEPS',  -- blocked on upstream subtask completion
    'COMPLETED',      -- all subtasks succeeded
    'PARTIALLY_FAILED', -- some subtasks failed, partial result available
    'FAILED',         -- terminal failure
    'CANCELLED'
);

CREATE TYPE agent_status AS ENUM (
    'IDLE',
    'PROCESSING',
    'DRAINING',   -- finishing current work before shutdown
    'OFFLINE'
);

-- Tenants (enterprise multi-tenancy)
CREATE TABLE tenants (
    tenant_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    tier            TEXT NOT NULL DEFAULT 'standard',  -- standard | premium | enterprise
    max_concurrency INT NOT NULL DEFAULT 10,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Parent tasks (top-level request from a client)
CREATE TABLE tasks (
    task_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
    idempotency_key TEXT UNIQUE,  -- client-supplied dedup key
    status          task_status NOT NULL DEFAULT 'PENDING',
    priority        SMALLINT NOT NULL DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
    payload         JSONB NOT NULL,          -- original request body
    result          JSONB,                   -- aggregated final result
    metadata        JSONB DEFAULT '{}',      -- routing hints, tags
    error_detail    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    ttl_seconds     INT DEFAULT 3600         -- auto-expire stale tasks
);

CREATE INDEX idx_tasks_tenant_status ON tasks (tenant_id, status);
CREATE INDEX idx_tasks_created       ON tasks (created_at DESC);

-- Subtasks (atomic units dispatched to agents)
CREATE TABLE subtasks (
    subtask_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),
    agent_type      TEXT NOT NULL,            -- e.g. 'rag', 'code', 'data_router'
    sequence_order  SMALLINT NOT NULL,        -- execution order within DAG level
    depends_on      UUID[] DEFAULT '{}',      -- subtask_ids this depends on
    status          task_status NOT NULL DEFAULT 'PENDING',
    input_payload   JSONB NOT NULL,           -- scoped input for the agent
    output_payload  JSONB,                    -- agent's response
    error_detail    TEXT,
    retry_count     SMALLINT NOT NULL DEFAULT 0,
    max_retries     SMALLINT NOT NULL DEFAULT 3,
    dispatched_at   TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_subtasks_task     ON subtasks (task_id);
CREATE INDEX idx_subtasks_status   ON subtasks (tenant_id, status);
CREATE INDEX idx_subtasks_deps     ON subtasks USING GIN (depends_on);

-- Agent registry (tracks live agent instances)
CREATE TABLE agents (
    agent_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type      TEXT NOT NULL,
    instance_id     TEXT NOT NULL UNIQUE,     -- k8s pod name or container id
    status          agent_status NOT NULL DEFAULT 'IDLE',
    capabilities    JSONB DEFAULT '[]',       -- list of supported task types
    current_load    SMALLINT NOT NULL DEFAULT 0,
    max_load        SMALLINT NOT NULL DEFAULT 5,
    last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT now(),
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agents_type_status ON agents (agent_type, status);

-- Audit log (append-only, immutable)
CREATE TABLE audit_log (
    log_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       UUID NOT NULL,
    task_id         UUID NOT NULL,
    subtask_id      UUID,
    event_type      TEXT NOT NULL,            -- e.g. 'TASK_CREATED', 'SUBTASK_DISPATCHED', 'AGENT_TIMEOUT'
    old_status      task_status,
    new_status      task_status,
    agent_id        UUID,
    detail          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_tenant_task ON audit_log (tenant_id, task_id);
CREATE INDEX idx_audit_created     ON audit_log (created_at DESC);

-- Row-Level Security for tenant isolation
ALTER TABLE tasks      ENABLE ROW LEVEL SECURITY;
ALTER TABLE subtasks   ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log  ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_tasks ON tasks
    USING (tenant_id = current_setting('app.current_tenant')::UUID);

CREATE POLICY tenant_isolation_subtasks ON subtasks
    USING (tenant_id = current_setting('app.current_tenant')::UUID);

CREATE POLICY tenant_isolation_audit ON audit_log
    USING (tenant_id = current_setting('app.current_tenant')::UUID);