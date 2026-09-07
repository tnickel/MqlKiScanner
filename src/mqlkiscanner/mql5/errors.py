"""Typed MQL5 outcomes shared by HTTP, browser and pipeline code."""


class Mql5CredentialsMissingError(RuntimeError):
    """No configured login: public precheck is possible, authenticated export is not."""


class Mql5AuthenticationError(RuntimeError):
    """Configured login was rejected or not confirmed; counts toward fail-fast."""
