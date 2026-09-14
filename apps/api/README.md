# Banboos 2.0 API

The first milestone exposes a read-only, versioned HTTP contract and a queued
run contract. It starts in demo mode so the server cannot accidentally read
the 1.6.6 production database.

```powershell
Set-Location E:\Banboos2.0
& .venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

To inspect an isolated legacy copy, set `BANBOOS2_LEGACY_DB` to that copied
SQLite file before starting the server. The adapter rejects the old default
`data\price_analysis.db` path by design.

OpenAPI is available at `http://127.0.0.1:8000/docs`.

`GET /api/v1/price/range?node_id=...&market=实时` returns the valid data
boundary for a node and market. The Web client uses this boundary to initialize
the date filters from the actual database instead of a hard-coded date.

Edge integration uses `POST /api/v1/telemetry/batches` for idempotent batch
ingest, `POST /api/v1/telemetry/batches/{batch_id}/ack` after a successful
upload, and `GET /api/v1/edge/{gateway_id}/heartbeat` for connection and spool
status. These endpoints only accept telemetry; production control remains
disabled.

`GET /api/v1/runs?kind=financial&status=succeeded` lists recent tasks for the
operations center. `GET /api/v1/telemetry/pending` exposes batch metadata and
pending point counts without returning telemetry values.

`GET /api/v1/alerts?unacknowledged_only=true` lists persisted telemetry alerts;
`POST /api/v1/alerts/{alert_id}/ack` acknowledges one alert. Alert handling is
traceable and read-only; it never issues a device command.

`GET /api/v1/telemetry/recent` returns recent telemetry points with optional
`station_id`, `device_id` and `point_id` filters for station detail pages.

Set `BANBOOS2_REDIS_URL` on both API and Worker processes to share queued task
state across processes. Without it, task execution is intentionally local to
the current process for development.
