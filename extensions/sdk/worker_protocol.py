"""Versioned JSON protocol shared by plugin workers and the host."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = "1.0"
PREVIOUS_PROTOCOL_VERSION = "0.9"
MAX_MESSAGE_BYTES = 4 * 1024 * 1024

CAP_REQUEST = "request"
CAP_PROGRESS = "progress"
CAP_CANCEL = "cancel"
CAP_DEADLINE = "deadline"
CAP_HEARTBEAT = "heartbeat"
CAP_STRUCTURED_ERROR = "structured_error"
HOST_CAPABILITIES = frozenset(
    {CAP_REQUEST, CAP_PROGRESS, CAP_CANCEL, CAP_DEADLINE, CAP_HEARTBEAT, CAP_STRUCTURED_ERROR}
)


class WorkerProtocolError(ValueError):
    code = "worker_protocol_error"


class WorkerProtocolTooNew(WorkerProtocolError):
    code = "worker_protocol_too_new"


class WorkerCapabilityMissing(WorkerProtocolError):
    code = "worker_capability_missing"


@dataclass(frozen=True)
class WorkerHello:
    protocol_version: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    worker_version: str = ""

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> WorkerHello:
        version = str(message.get("protocol_version") or PREVIOUS_PROTOCOL_VERSION)
        raw_capabilities = message.get("capabilities") or [CAP_REQUEST]
        if not isinstance(raw_capabilities, list):
            raise WorkerProtocolError("worker capabilities must be a list")
        return cls(
            protocol_version=version,
            capabilities=frozenset(str(item) for item in raw_capabilities if str(item)),
            worker_version=str(message.get("worker_version") or ""),
        )


def negotiate_worker(message: dict[str, Any], required_capabilities: Iterable[str] = ()) -> WorkerHello:
    hello = WorkerHello.from_message(message)
    if hello.protocol_version not in {PROTOCOL_VERSION, PREVIOUS_PROTOCOL_VERSION}:
        try:
            current_major = int(PROTOCOL_VERSION.split(".", 1)[0])
            worker_major = int(hello.protocol_version.split(".", 1)[0])
        except ValueError as exc:
            raise WorkerProtocolError(f"invalid worker protocol version: {hello.protocol_version}") from exc
        if worker_major > current_major:
            raise WorkerProtocolTooNew(f"worker protocol is newer than host: {hello.protocol_version}")
        raise WorkerProtocolError(f"unsupported worker protocol: {hello.protocol_version}")
    missing = set(required_capabilities) - set(hello.capabilities)
    if missing:
        raise WorkerCapabilityMissing("worker missing capabilities: " + ", ".join(sorted(missing)))
    return hello


def ready_message(token: str, *, worker_version: str = "") -> dict[str, Any]:
    return {
        "type": "ready",
        "token": token,
        "protocol_version": PROTOCOL_VERSION,
        "capabilities": sorted(HOST_CAPABILITIES),
        "worker_version": worker_version,
    }


def structured_error(code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
    return {"code": str(code), "message": str(message), "retryable": bool(retryable)}
