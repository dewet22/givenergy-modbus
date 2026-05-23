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
