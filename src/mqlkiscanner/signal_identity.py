"""Explicit signal identity: external IDs are never internal database references."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class IdentityError(ValueError):
    pass


class AmbiguousSignalIdentity(IdentityError):
    pass


class IdentityMigrationRequired(IdentityError):
    pass


def _field(value, name, default=None):
    if isinstance(value, Mapping):
        return value.get(name, default)
    if hasattr(value,"keys") and name in value.keys():
        return value[name]
    return getattr(value, name, default)


def source_label(value) -> str:
    label = str(value or "")
    return label if label.strip() else "mql5"


def identity_key(value) -> tuple[str, int]:
    """Current presentation alias + external ID, never a persistent owner key."""
    source = source_label(_field(value,"signal_quelle") or _field(value,"datenquelle")
                          or _field(value,"quelle_kuerzel") or _field(value,"quelle"))
    from . import db
    source = db.kanonische_quelle(source)
    external = _field(value, "signal_id")
    if external is None:
        external = _field(value, "id")
    return source, int(external)


key_for = identity_key


def stable_identity_key(value) -> tuple:
    ref = _field(value, "signal_ref")
    if ref is not None:
        return "ref", int(ref)
    uid = _field(value, "quellen_uid")
    if uid:
        external = _field(value, "signal_id")
        if external is None:
            external = _field(value, "id")
        return "source", str(uid), int(external)
    return identity_key(value)


@dataclass(frozen=True)
class SignalIdentity:
    quelle: str
    signal_id: int
    signal_ref: int | None = None
    quellen_uid: str = ""

    @property
    def signal_key(self) -> tuple[str, int]:
        return identity_key(self)
