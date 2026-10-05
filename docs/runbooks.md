# Runbooks

Every alert links here. Each entry: what it means, what to check first, and how to fix the usual
causes. Keep them short enough to follow at 3 am.

## TargetDown

**Means:** Prometheus can't scrape a service's `/metrics` for over a minute. Either the service is
down or the network path to it is.

1. Grafana → **Platform overview** → *Service availability*: one service, or all of a product?
   All at once usually means the host or the network, not the code.
2. `docker compose ps` (or `kubectl get pods`) for that service: running, restarting, or exited?
3. `docker compose logs --tail 100 <service>`: the last error before it stopped.
4. Restart it: `docker compose up -d <service>`. If it keeps restarting, see **ContainerRestarting**.

## ProbeFailed

**Means:** the outside-in HTTP check of a page or health endpoint has failed for 2 minutes. Users
are probably affected.

1. Open the URL in a browser. Down for everyone, or only from the monitoring host?
2. Grafana → **Uptime and certificates** → *Response time by phase*: DNS, connect, TLS or server?
   DNS or TLS failures point at Cloudflare/certificates; server time points at the application.
3. For darviq.com: Cloudflare Pages deployments page; roll back the last deploy if it broke.

## SlowResponse

**Means:** a checked page has averaged over 2 s for 5 minutes.

1. *Response time by phase*: if `processing` dominates, look at the application's p95 latency
   (Platform overview); if `connect`/`tls` dominates, it is network or edge.

## TLSCertificateExpiringSoon

**Means:** a certificate expires in under 14 days. Automatic renewal (Caddy, Cloudflare) has
probably failed.

1. Check the renewal logs (`docker compose logs caddy`) for ACME errors: usually DNS no longer
   points at the server, or port 80 is blocked.
2. Fix the cause, then force a renewal (restart Caddy).

## HighErrorRate

**Means:** over 5% of a service's requests have returned 5xx for 5 minutes, under real traffic.

1. Platform overview → *Responses by status code* and *Error ratio by service*: which service?
2. Its logs for the stack trace. If it started right after a deploy, roll back first, then debug.
3. If its dependency is down (database, message broker), fix that: the service is only the messenger.

## HighLatencyP95

**Means:** the slowest 5% of a service's requests have taken over 500 ms for 10 minutes.

1. Hosts and containers: is the host CPU- or memory-bound? Then it's capacity.
2. Otherwise a slow dependency (database query, downstream service): check that service's p95.

## DiskSpaceLow

**Means:** a filesystem is under 15% free (warning) or 5% (critical).

1. Hosts and containers → *Free space by filesystem*: which mount.
2. Usual suspects: Docker images and build cache (`docker system df`, then
   `docker image prune`), container logs without rotation, old database backups.

## DiskWillFillIn24h

**Means:** at the rate of the last 6 hours, a disk is full within a day. This is the early
warning: it fires while there is still space, so there is time to act calmly.

1. *Hours until full at the current rate*: confirm the trend isn't a one-off (a large copy).
2. Find what is writing (`du -sh /var/lib/docker/* | sort -h`, application logs) and stop or
   rotate it, or grow the volume.

## HighCPU

**Means:** the host has been over 90% busy for 15 minutes.

1. Container CPU (top 10): one container, or everything? One container usually means a loop or a
   traffic spike to that service.

## MemoryPressure

**Means:** the host is using over 90% of its memory for 10 minutes; the kernel will soon start
killing processes.

1. Container memory (top 10): look for one that only grows (a leak); restart it as a stopgap.

## ContainerRestarting

**Means:** a container crashed and Docker's restart policy restarted it in the last 15 minutes.
Deliberate stops, starts and redeploys don't trigger it.

1. `docker compose logs --tail 200 <name>`: the crash just before the restart.
2. Often a dependency wasn't ready at startup (database, broker): check health-check timings.

## ErrorLogSpike

**Means:** a service has logged more than 20 error-level lines in 5 minutes (from Loki).

1. Grafana → **Logs** → filter to the service and level `error`: one repeated error, or many kinds?
2. One repeated error usually has a single cause (a dependency down, bad config after a deploy):
   match its first occurrence to the deploy or incident timeline.

## CrashLoopInLogs

**Means:** a service has logged several stack traces or unhandled exceptions in 10 minutes.

1. Grafana → **Logs**, search `Traceback` or `exception` for the service: the first stack trace
   is the useful one.
2. Check **ContainerRestarting** and the service's error ratio: is it actually failing requests?

## Watchdog

**Means:** nothing is wrong. It always fires, so the on-call side receives a heartbeat. If the
heartbeat **stops** arriving, the alerting pipeline itself is broken: check Prometheus →
Alertmanager → receiver, in that order.
