# Local dev infra

Compose stack for local development: Postgres 16, Redis 7, Temporal (with UI),
and MinIO (S3-compatible).

## Usage

```bash
docker compose -f infra/docker/dev.yml up -d
docker compose -f infra/docker/dev.yml down
```

Or via the root Makefile: `make up` / `make down`.

## Endpoints

| Service      | URL                              | Credentials         |
| ------------ | -------------------------------- | ------------------- |
| Postgres     | `postgres://voyagent:voyagent@localhost:5432/voyagent` | user: `voyagent` / pw: `voyagent` |
| Redis        | `redis://localhost:6379`         | (none)              |
| Temporal     | `localhost:7233` (gRPC)          | (none, dev)         |
| Temporal UI  | http://localhost:8088            | (none, dev)         |
| MinIO S3     | http://localhost:9000            | `voyagent` / `voyagent` |
| MinIO console| http://localhost:9001            | `voyagent` / `voyagent` |

All data persists in named volumes (`voyagent-postgres-data`,
`voyagent-redis-data`, `voyagent-minio-data`). Wipe with
`docker compose -f infra/docker/dev.yml down -v`.
