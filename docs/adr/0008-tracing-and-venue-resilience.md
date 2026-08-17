# 8. Distributed tracing and a circuit-broken venue client

**Status:** Accepted

## Context
The platform is several cooperating services (OMS, risk service) tied together by an asynchronous Kafka
stream and, at the edges, by synchronous calls to an external broker (Alpaca). Two gaps followed from
that shape:

- **Observability across a boundary.** A per-request `correlationId` (SLF4J MDC) tagged logs *within* a
  service, but nothing tied one order's flow *across* the HTTP call, the `order-events` topic, and the
  risk consumer. When something is slow or wrong, "which log lines belong to this one order, everywhere"
  had no answer.
- **A synchronous dependency with no failure policy.** The Alpaca client called the venue with a plain
  timeout. A brief broker outage meant every caller blocked on its own timeout in turn, and a genuinely
  invalid order (a 4xx) was handled the same as a transient blip (a 5xx) — no distinction between "retry
  might help" and "retrying can only ever fail."

## Decision
**Tracing.** Adopt Micrometer Tracing (Brave bridge) in both services. Every request gets a
`traceId`/`spanId` in its logs, propagated over HTTP via the W3C `traceparent`. Kafka observation is
enabled on the producer template and the listener container, so the trace context rides the record
headers: consuming an order event is a *child span* of the OMS request that produced it — one trace
spanning the OMS, the topic, and the risk service. No exporter is bundled, so this is inert (ids in the
logs only) until `management.zipkin.tracing.endpoint` points at a collector. The `correlationId` stays as
the client-facing edge id; `traceId` is the internal cross-service one.

**Resilience.** Guard every outbound Alpaca call with one shared Resilience4j **circuit breaker + retry**
(configured in `application.yml`, state bound to metrics and actuator health). The change that makes it
correct is *error classification*:
- transient failures — IO/timeout/5xx, and a fail-fast when the breaker is open — become a
  `BrokerUnavailableException`, which **is** retried and **does** count toward the breaker;
- a terminal 4xx becomes a `BrokerRejectedException`, which is **neither** retried **nor** counted,
  because retrying a rejected order would never succeed and would falsely trip the breaker.

The policy is applied programmatically (decorated suppliers), not by annotation, so the whole thing is
unit-testable against a local HTTP server without a Spring context — retry-recovers, 4xx-is-terminal,
and breaker-opens-then-fails-fast are all asserted deterministically.

## Consequences
- **Gain:** one order's lifecycle is a single trace across the service boundary; a flaky broker fails
  fast for all callers instead of hanging each one, while the breaker stays blind to mere business
  rejections. Breaker state and retry counts show up in Prometheus and `/actuator/health` for free.
- **Cost:** two more dependencies per service and a shared breaker whose window is tuned in config; the
  cross-Kafka propagation is exercised in the Dockerized integration path (CI), since it needs a broker.
- **Bug found on the way in:** a `@PreAuthorize` denial had been surfacing as `500` because the
  catch-all `@RestControllerAdvice` swallowed Spring Security's `AccessDeniedException`; classifying it
  as `403` is the analogous "don't mask a known condition as a server fault" fix on the inbound side.
