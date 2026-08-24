from collections import Counter, deque
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic


@dataclass
class Metrics:
    request_count: Counter[tuple[str, str]] = field(default_factory=Counter)
    request_errors: Counter[str] = field(default_factory=Counter)
    request_durations: list[float] = field(default_factory=list)
    index_tasks: Counter[str] = field(default_factory=Counter)
    retrieval_durations: list[float] = field(default_factory=list)
    model_first_token_durations: list[float] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def observe_request(self, path: str, status_code: int, duration_seconds: float) -> None:
        with self._lock:
            self.request_count[(path, str(status_code))] += 1
            if status_code >= 400:
                self.request_errors[path] += 1
            self.request_durations.append(duration_seconds)

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP rag_http_requests_total HTTP requests by path and status.",
                "# TYPE rag_http_requests_total counter",
            ]
            lines.extend(
                f'rag_http_requests_total{{path="{path}",status="{status}"}} {count}'
                for (path, status), count in sorted(self.request_count.items())
            )
            lines.extend(
                [
                    "# HELP rag_http_errors_total HTTP errors by path.",
                    "# TYPE rag_http_errors_total counter",
                ]
            )
            lines.extend(
                f'rag_http_errors_total{{path="{path}"}} {count}'
                for path, count in sorted(self.request_errors.items())
            )
            lines.extend(
                [
                    "# HELP rag_index_tasks_total Document index tasks by outcome.",
                    "# TYPE rag_index_tasks_total counter",
                ]
            )
            lines.extend(
                f'rag_index_tasks_total{{status="{status}"}} {count}'
                for status, count in sorted(self.index_tasks.items())
            )
            return "\n".join(lines) + "\n"


class IpRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def allow(self, client_ip: str, category: str, limit: int, window_seconds: int) -> int | None:
        now = monotonic()
        key = (client_ip, category)
        with self._lock:
            entries = self._requests.setdefault(key, deque())
            while entries and entries[0] <= now - window_seconds:
                entries.popleft()
            if len(entries) >= limit:
                return max(1, int(window_seconds - (now - entries[0])) + 1)
            entries.append(now)
        return None
