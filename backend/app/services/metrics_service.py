"""
Operational Metrics and Monitoring Service for DMS.

Tracks and aggregates production telemetry in-memory with thread safety:
  1. API request rates, latency percentiles (p50, p95, p99), error rate distributions (2xx, 4xx, 5xx).
  2. Background job processing durations, active worker queue lag, and failure rates.
  3. AI provider token consumption, latency distributions, and provider failover counts.
  4. Security events: failed login attempts, MFA challenges, rate-limit hits, cross-tenant/cross-branch blocks.
  5. Dual-export formats: Clean JSON summary (/api/metrics) and standard Prometheus exposition (/metrics).
"""

import math
import statistics
import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional


class MetricsService:
    """Thread-safe telemetry collector and metrics aggregator."""

    def __init__(self, max_latency_samples: int = 5000):
        self._lock = threading.Lock()
        self._max_samples = max_latency_samples
        self.reset()

    def reset(self) -> None:
        """Reset all counters, histograms, and event buffers."""
        with self._lock:
            self._start_time = time.time()

            # HTTP Request Metrics
            self._http_requests_total = defaultdict(int)  # (method, status_code) -> count
            self._http_latencies_ms: List[float] = []

            # Background Job Metrics
            self._jobs_total = defaultdict(int)  # (job_type, status) -> count
            self._job_latencies_ms = defaultdict(list)  # job_type -> list of latencies

            # AI Provider Telemetry
            self._ai_requests_total = defaultdict(int)  # (provider, model, status) -> count
            self._ai_tokens_total = defaultdict(int)  # (provider, token_type) -> count
            self._ai_latencies_ms = defaultdict(list)  # provider -> list of latencies
            self._ai_fallbacks_total = defaultdict(int)  # (from_provider, to_provider) -> count

            # Security Events
            self._security_events_total = defaultdict(int)  # event_type -> count

    # ── HTTP Recording ────────────────────────────────────────────────────────

    def record_http_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        """Record an incoming HTTP request execution."""
        status_family = f"{status_code // 100}xx"
        with self._lock:
            self._http_requests_total[(method.upper(), status_code, status_family)] += 1
            if len(self._http_latencies_ms) < self._max_samples:
                self._http_latencies_ms.append(duration_ms)
            else:
                # Reservoir sampling / circular buffer replacement
                self._http_latencies_ms[int(time.time() * 1000) % self._max_samples] = duration_ms

    # ── AI Recording ──────────────────────────────────────────────────────────

    def record_ai_request(
        self,
        provider: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: float,
        success: bool = True,
    ) -> None:
        """Record an AI provider extraction or inference invocation."""
        status_str = "success" if success else "failure"
        with self._lock:
            self._ai_requests_total[(provider, model, status_str)] += 1
            self._ai_tokens_total[(provider, "input")] += max(0, tokens_in)
            self._ai_tokens_total[(provider, "output")] += max(0, tokens_out)
            samples = self._ai_latencies_ms[provider]
            if len(samples) < self._max_samples:
                samples.append(latency_ms)
            else:
                samples[int(time.time() * 1000) % self._max_samples] = latency_ms

    def record_ai_fallback(self, from_provider: str, to_provider: str, reason: str = "") -> None:
        """Record an automated AI provider failover event."""
        with self._lock:
            self._ai_fallbacks_total[(from_provider, to_provider)] += 1

    # ── Job Queue Recording ───────────────────────────────────────────────────

    def record_job_execution(self, job_type: str, duration_ms: float, success: bool = True) -> None:
        """Record a background job execution."""
        status_str = "success" if success else "failure"
        with self._lock:
            self._jobs_total[(job_type, status_str)] += 1
            samples = self._job_latencies_ms[job_type]
            if len(samples) < self._max_samples:
                samples.append(duration_ms)
            else:
                samples[int(time.time() * 1000) % self._max_samples] = duration_ms

    # ── Security Event Recording ──────────────────────────────────────────────

    def record_security_event(self, event_type: str) -> None:
        """
        Record a security-critical event:
          - failed_login
          - cross_tenant_attempt
          - cross_branch_attempt
          - mfa_challenge_failed
          - rate_limit_exceeded
          - file_validation_blocked
        """
        with self._lock:
            self._security_events_total[event_type] += 1

    # ── Percentile Calculation Helper ─────────────────────────────────────────

    @staticmethod
    def _compute_percentiles(values: List[float]) -> Dict[str, float]:
        if not values:
            return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0, "count": 0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def percentile(p: float) -> float:
            idx = int(math.ceil((p / 100.0) * n)) - 1
            return round(sorted_vals[max(0, min(idx, n - 1))], 2)

        return {
            "p50": percentile(50),
            "p90": percentile(90),
            "p95": percentile(95),
            "p99": percentile(99),
            "avg": round(sum(sorted_vals) / n, 2),
            "count": n,
        }

    # ── Structured JSON Summary ───────────────────────────────────────────────

    def get_summary(self) -> Dict[str, Any]:
        """Return a structured JSON dictionary of all telemetry metrics."""
        with self._lock:
            uptime_seconds = round(time.time() - self._start_time, 1)

            # Summarize HTTP
            total_http = sum(self._http_requests_total.values())
            http_by_family = defaultdict(int)
            for (_, _, family), count in self._http_requests_total.items():
                http_by_family[family] += count

            http_latency_stats = self._compute_percentiles(self._http_latencies_ms)

            # Summarize AI
            ai_providers = {}
            all_providers = {k[0] for k in self._ai_requests_total.keys()} | {k[0] for k in self._ai_tokens_total.keys()}
            for prov in all_providers:
                prov_reqs = sum(c for k, c in self._ai_requests_total.items() if k[0] == prov)
                prov_fails = sum(c for k, c in self._ai_requests_total.items() if k[0] == prov and k[2] == "failure")
                prov_lat = self._compute_percentiles(self._ai_latencies_ms.get(prov, []))
                ai_providers[prov] = {
                    "requests_total": prov_reqs,
                    "failures_total": prov_fails,
                    "tokens_input": self._ai_tokens_total.get((prov, "input"), 0),
                    "tokens_output": self._ai_tokens_total.get((prov, "output"), 0),
                    "latency_stats": prov_lat,
                }

            fallbacks = [
                {"from": k[0], "to": k[1], "count": v}
                for k, v in self._ai_fallbacks_total.items()
            ]

            # Summarize Jobs
            jobs = {}
            for (jtype, status_str), count in self._jobs_total.items():
                if jtype not in jobs:
                    jobs[jtype] = {"success": 0, "failure": 0, "latency": self._compute_percentiles(self._job_latencies_ms.get(jtype, []))}
                jobs[jtype][status_str] += count

            # Summarize Security
            sec_events = dict(self._security_events_total)

            return {
                "uptime_seconds": uptime_seconds,
                "http": {
                    "total_requests": total_http,
                    "status_breakdown": dict(http_by_family),
                    "latency_stats": http_latency_stats,
                },
                "ai": {
                    "providers": ai_providers,
                    "fallbacks": fallbacks,
                },
                "jobs": jobs,
                "security": sec_events,
            }

    # ── Prometheus Exposition Format ──────────────────────────────────────────

    def to_prometheus(self) -> str:
        """Export metrics formatted for Prometheus scrapers."""
        lines = []
        summary = self.get_summary()

        # DMS Uptime
        lines.append("# HELP dms_uptime_seconds Total application process uptime in seconds.")
        lines.append("# TYPE dms_uptime_seconds gauge")
        lines.append(f"dms_uptime_seconds {summary['uptime_seconds']}")

        # HTTP Requests Total
        lines.append("# HELP dms_http_requests_total Total number of HTTP requests processed.")
        lines.append("# TYPE dms_http_requests_total counter")
        with self._lock:
            for (method, code, family), count in sorted(self._http_requests_total.items()):
                lines.append(f'dms_http_requests_total{{method="{method}",status="{code}",family="{family}"}} {count}')

        # HTTP Latencies
        http_lat = summary["http"]["latency_stats"]
        lines.append("# HELP dms_http_request_duration_ms HTTP request latency percentiles in milliseconds.")
        lines.append("# TYPE dms_http_request_duration_ms gauge")
        lines.append(f'dms_http_request_duration_ms{{quantile="0.50"}} {http_lat["p50"]}')
        lines.append(f'dms_http_request_duration_ms{{quantile="0.90"}} {http_lat["p90"]}')
        lines.append(f'dms_http_request_duration_ms{{quantile="0.95"}} {http_lat["p95"]}')
        lines.append(f'dms_http_request_duration_ms{{quantile="0.99"}} {http_lat["p99"]}')

        # AI Metrics
        lines.append("# HELP dms_ai_requests_total Total AI extraction and LLM inference calls.")
        lines.append("# TYPE dms_ai_requests_total counter")
        with self._lock:
            for (provider, model, status_str), count in sorted(self._ai_requests_total.items()):
                lines.append(f'dms_ai_requests_total{{provider="{provider}",model="{model}",status="{status_str}"}} {count}')

        lines.append("# HELP dms_ai_tokens_total Total tokens consumed by AI providers.")
        lines.append("# TYPE dms_ai_tokens_total counter")
        with self._lock:
            for (provider, token_type), count in sorted(self._ai_tokens_total.items()):
                lines.append(f'dms_ai_tokens_total{{provider="{provider}",type="{token_type}"}} {count}')

        lines.append("# HELP dms_ai_fallbacks_total Total automated AI provider failovers triggered.")
        lines.append("# TYPE dms_ai_fallbacks_total counter")
        with self._lock:
            for (from_p, to_p), count in sorted(self._ai_fallbacks_total.items()):
                lines.append(f'dms_ai_fallbacks_total{{from_provider="{from_p}",to_provider="{to_p}"}} {count}')

        # Security Events
        lines.append("# HELP dms_security_events_total Total security-relevant authorization and authentication events.")
        lines.append("# TYPE dms_security_events_total counter")
        with self._lock:
            for event_type, count in sorted(self._security_events_total.items()):
                lines.append(f'dms_security_events_total{{event_type="{event_type}"}} {count}')

        # Job Queue
        lines.append("# HELP dms_background_jobs_total Total background asynchronous jobs executed.")
        lines.append("# TYPE dms_background_jobs_total counter")
        with self._lock:
            for (jtype, status_str), count in sorted(self._jobs_total.items()):
                lines.append(f'dms_background_jobs_total{{job_type="{jtype}",status="{status_str}"}} {count}')

        return "\n".join(lines) + "\n"


# Singleton instance
metrics_service = MetricsService()
