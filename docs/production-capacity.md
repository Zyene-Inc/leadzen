# Repeatable bounded capacity check

`tests/scenarios/production_capacity.py` seeds only a new empty private fixture,
starts the installed candidate under the reviewed one-worker/eight-thread Gunicorn
configuration, then measures concurrent bounded CRM/overview/settings reads and
settings writes across employees. It verifies integrity and foreign keys after
shutdown. It never invokes email, AI, enrichment, invitations or MCP tools.
Network egress must be disabled by the container, and automation flags are off.

Run the exact candidate image on the intended architecture with a new directory:

```sh
fixture=$(mktemp -d /srv/private/leadzen-capacity.XXXXXX)
chmod 700 "$fixture"
# Set this new fixture's owner to the image's dedicated runtime UID/GID only.
sudo chown 1000:1000 "$fixture"
docker run --rm --network none --platform linux/amd64 \
  -e LEADZEN_CAPACITY_NETWORK_ISOLATED=1 \
  -v "$fixture:/app/data/leadzen-capacity.fixture" \
  -v "$candidate/source/tests/scenarios/production_capacity.py:/verification/capacity.py:ro" \
  "$image_digest" /opt/venv/bin/python /verification/capacity.py \
  --root /app/data/leadzen-capacity.fixture --employees 4 --contacts 5000 \
  --concurrency 16 --requests 256
```

The report contains only sizes/counts, error totals, latency percentiles, throughput
and post-run integrity. Private server logs stay in the fixture. A successful local
emulated run is a regression result; actual VM CPU/RAM/disk, proxy limits, long
poll/SSE connections, dashboard request budgets and accepted operational thresholds
remain a target-host gate. Increase volume/concurrency within the explicit bounds
only after defining expected traffic and latency/error budgets. Inspect disk/memory
and SQLite lock alarms during the authorized target-host run.
