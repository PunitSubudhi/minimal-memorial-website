# Report: "SSL connection has been closed unexpectedly" during tribute photo queries

**Date:** 2025-11-11  
**Environment:** EC2-hosted Gunicorn workers querying Neon Postgres via SQLAlchemy + psycopg3  
**Observed By:** `tail gunicorn.log` (production)

## Incident Summary
- Request path: carousel/tribute photo fetch (randomized query used on `/tributes` and home hero component).
- Failure: Flask request aborts with `sqlalchemy.exc.OperationalError`, root message `psycopg.OperationalError: consuming input failed: SSL connection has been closed unexpectedly`.
- Query: `SELECT ... FROM tribute_photos WHERE photo_b64 IS NOT NULL ORDER BY random() LIMIT 24`.
- Impact: Affects end-user page loads that need gallery imagery (pages render without photos and log stack traces, increasing error rates). No data loss detected.

## Technical Diagnosis
### What happened
1. Gunicorn worker pulls a pooled database connection from SQLAlchemy's default pool (permanent connection established earlier).
2. Neon serverless compute idles out (e.g., after ~5 minutes of inactivity) and terminates underlying TLS session to reclaim resources.
3. SQLAlchemy is unaware the socket died because no health check is configured.
4. When the next request issues a query, psycopg attempts to use the stale socket; Neon has already closed it, so TLS decryption fails and psycopg surfaces `SSL connection has been closed unexpectedly`.
5. SQLAlchemy bubbles the failure as an `OperationalError`. Because this occurs mid-request, the response surface is a 500 error and Gunicorn logs the stack trace shown above.

### Contributing factors
- **No pre-ping/keepalive.** `SQLALCHEMY_ENGINE_OPTIONS` does not enable `pool_pre_ping`, so stale connections are not detected before use.
- **Serverless DB behavior.** Neon auto-pause aggressively; idle connections are closed without warning, which requires application-side resiliency.
- **Gunicorn worker model.** Workers maintain long-lived engine connections and do not automatically recycle them, amplifying the impact of the missing health checks.
- **Large payload column (`photo_b64`).** Fetching many base64 blobs makes each reconnect costlier, but is not the primary trigger; nevertheless, the query magnifies visibility of the fault.

## Recommended Remediation
1. **Enable connection health checks** in app configuration:
   - Set `SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 300, "pool_timeout": 30}` (tune values to taste). `pool_pre_ping` forces SQLAlchemy to test each connection before handing it to the request, transparently discarding stale sessions.
   - Optionally add `engine_options={"connect_args": {"sslmode": "require"}}` if not already enforced in the URI to match Neon's TLS expectations.
2. **Deploy** the configuration change and restart Gunicorn. Monitor for recurrence (expectation: first query after idle now triggers a transparent reconnect, not an error).
3. **Add runtime alerting** for repeated `OperationalError` occurrences so regressions are detected quickly.

## Verification Plan
- **Local reproduction:** Simulate by idling the app for >5 minutes, then request `/tributes`. Without fix, error reproduces; with fix, page loads successfully and logs show the pool silently recycling.
- **Staging test:** Push configuration to staging, idle for the same window, confirm first request succeeds and no errors surface in logs.
- **Production monitoring:** After deploying, watch Gunicorn logs and Neon metrics for 24h. Error rate should drop to zero; if not, collect new stack traces.

## Longer-Term Considerations
- Evaluate using `NullPool` or `StaticPool` for truly serverless-friendly behavior if request rate remains low, trading pooled connections for per-request connections.
- Consider shifting heavy binary storage (`photo_b64`) to object storage (S3) to reduce query payload and reliance on large blob columns.
- Document the Neon auto-suspend behavior in deployment runbooks and ensure engineers know to expect TLS drops when idle.

## References
- SQLAlchemy docs: [Pooling / Disconnect Handling](https://docs.sqlalchemy.org/en/20/core/pooling.html#pool-disconnects)
- Neon documentation: [Connection limits & autosuspend](https://neon.tech/docs/connect/neon-protocol#connection-limits)
- psycopg3 `OperationalError`: https://www.psycopg.org/psycopg3/docs/api/errors.html#psycopg.errors.OperationalError
