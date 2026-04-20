# Nexus Orchestrator — Architecture

## System Architecture (Mermaid)

```mermaid
flowchart TB
    subgraph API_LAYER["API Layer (FastAPI)"]
        GW[API Gateway<br/>Auth / Rate Limit / Tenant Isolation]
    end

    subgraph ORCHESTRATOR["Orchestrator Core"]
        TD[Task Decomposer]
        SM[State Machine]
        DP[Dispatcher]
        RC[Response Collector]
    end

    subgraph EVENT_BUS["Event Bus (Kafka)"]
        TQ[task.dispatch<br/>topic]
        RQ[task.result<br/>topic]
        DLQ[task.dlq<br/>dead-letter]
    end

    subgraph AGENTS["Specialized Agent Pool"]
        A1[RAG Agent]
        A2[Code Agent]
        A3[Data Router Agent]
        A4[Summarizer Agent]
        AN[Agent N...]
    end

    subgraph PERSISTENCE["Persistence Layer"]
        RD[(Redis<br/>Ephemeral State)]
        PG[(PostgreSQL<br/>Audit + Task Log)]
        VDB[(Vector DB<br/>Long-term Context)]
    end

    %% Request flow
    GW -->|"POST /tasks"| TD
    TD -->|"decompose"| SM
    SM -->|"subtasks"| DP
    DP -->|"publish"| TQ

    %% Agent consumption
    TQ --> A1 & A2 & A3 & A4 & AN
    A1 & A2 & A3 & A4 & AN -->|"publish result"| RQ
    A1 & A2 & A3 & A4 & AN -.->|"failed after retries"| DLQ

    %% Result flow
    RQ -->|"consume"| RC
    RC -->|"update state"| SM
    SM -->|"if all subtasks done"| GW

    %% State reads/writes
    SM <-->|"read/write task state"| RD
    SM -->|"write audit log"| PG
    A1 <-->|"RAG queries"| VDB
    RC -->|"persist result"| PG
```

## Data Flow Summary

1. **Ingest**: Client hits the API Gateway with a complex task payload.
2. **Decompose**: The Orchestrator's Task Decomposer breaks the payload into
   atomic subtasks using a DAG (directed acyclic graph) of dependencies.
3. **Dispatch**: Each subtask is serialized and published to the Kafka
   `task.dispatch` topic, keyed by `tenant_id` for ordered processing per tenant.
4. **Execute**: Specialized agents consume from their assigned partitions,
   execute, and publish results to `task.result`.
5. **Collect**: The Response Collector consumes results, updates the state
   machine in Redis, and writes audit records to PostgreSQL.
6. **Complete**: When all subtasks for a parent task reach terminal state
   (COMPLETED / FAILED), the orchestrator finalizes the response.

## Tenant Isolation Strategy

- Kafka partition key = `tenant_id` (ordering guarantee per tenant)
- Redis key prefix = `tenant:{tenant_id}:task:{task_id}`
- PostgreSQL Row-Level Security (RLS) on `tenant_id` column
- API Gateway extracts tenant from JWT and injects into request context