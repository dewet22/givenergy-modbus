from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from givenergy_modbus.model.plant import Plant


class ExceptionBase(Exception):
    """Base exception."""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidPduState(ExceptionBase):
    """Thrown during PDU self-validation."""

    def __init__(self, message: str, pdu) -> None:
        super().__init__(message=message)
        self.pdu = pdu


class InvalidFrame(ExceptionBase):
    """Thrown during framing when a message cannot be extracted from a frame buffer."""

    frame: bytes

    def __init__(self, message: str, frame: bytes) -> None:
        super().__init__(message=message)
        self.frame = frame


class CommunicationError(ExceptionBase):
    """Exception to indicate a communication error."""


class PlantNotDetected(CommunicationError):
    """Raised when a capability-aware poll is attempted before ``detect()`` has run.

    ``load_config()`` / ``refresh()`` route by ``plant.capabilities`` (device kind,
    inverter address, slot layout). With no capabilities there is no safe default —
    guessing an inverter address (historically ``0x32``) silently times out on models
    that answer elsewhere (e.g. an All-in-One at ``0x11``). Rather than guess, the poll
    refuses: call ``detect()`` once first, or restore a persisted ``PlantCapabilities``
    onto ``client.plant.capabilities`` before polling.
    """


class PlantTopologyMismatch(CommunicationError):
    """Raised when detect(prior=...) finds the plant doesn't match the supplied prior.

    Carries both `prior` (what the caller asserted) and `actual` (a PlantCapabilities
    reflecting what confirmed on this run). On raise, the Client's plant.capabilities
    is left as None — callers that wish to accept the new topology must explicitly
    assign `client.plant.capabilities = exc.actual`.

    Caller policy decides whether to retry (e.g. with longer timeouts), fall back to
    detect() without prior, or surface the change to the user.
    """

    def __init__(
        self,
        message: str,
        prior,
        actual,
    ) -> None:
        super().__init__(message=message)
        self.prior = prior
        self.actual = actual


class ReadFailure(NamedTuple):
    """Identifies a single register read that failed (after retries) during a poll.

    Structured so a consumer can reason about *which* device and bank dropped
    (e.g. "battery 0x34 is offline") without parsing log lines.
    """

    device_address: int
    request_type: str
    base_register: int
    register_count: int


class RefreshError(CommunicationError):
    """Base for a refresh()/load_config() that did not fully succeed.

    Carries the structured set of reads that failed (``failures``) plus the raw
    underlying exceptions grouped as an ``ExceptionGroup`` (``cause``) for
    tracebacks / drill-down.
    """

    failures: list[ReadFailure]
    cause: ExceptionGroup

    def __init__(self, message: str, failures: list[ReadFailure], cause: ExceptionGroup) -> None:
        super().__init__(message=message)
        self.failures = failures
        self.cause = cause


class RefreshPartiallySucceeded(RefreshError):
    """Some — but not all — register reads in a poll failed.

    The data that *was* collected is attached as ``plant``. This exception is
    the consumer's one opportunity to do something useful with that partial
    data — cache it, surface it, count the gap — before deciding how to treat
    the missing reads. Catching it and carrying on (even ignoring it) is a
    legitimate choice; the point is that it's the *consumer's* choice, made
    here, rather than something the library silently decided for them.
    """

    plant: Plant

    def __init__(self, message: str, plant: Plant, failures: list[ReadFailure], cause: ExceptionGroup) -> None:
        super().__init__(message=message, failures=failures, cause=cause)
        self.plant = plant


class RefreshFailed(RefreshError):
    """Every register read in the poll failed — the link is effectively dead.

    No usable data came back, so (unlike ``RefreshPartiallySucceeded``) there is
    no partial plant to hand over; callers should treat the device as
    unavailable.
    """
