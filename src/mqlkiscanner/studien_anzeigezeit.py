"""Display stored study wall-clock coordinates without inventing a timezone."""
from collections.abc import Mapping
from datetime import datetime, timezone


def zeitachsen_label(daten: Mapping | None = None) -> str:
    """Only the persisted frame identifies the domain of the displayed points."""
    basis = daten.get("zeitbasis") if isinstance(daten, Mapping) else None
    frame = basis.get("frame") if isinstance(basis, Mapping) else None
    if not isinstance(frame, str):
        return "Zeitbasis unbekannt"
    return {"broker": "CSV-/Brokerzeit",
            "referenzkurszeit": "Referenzkurszeit (MT5-H1)"}.get(frame, "Zeitbasis unbekannt")


def als_anzeigezeit(epoch):
    """Decode pseudoepochs identically on all hosts, without asserting UTC.

    Broker-frame points encode CSV wall time; a normalized study can encode
    reference-feed time instead. Neither is shifted by display formatting.
    """
    if epoch is None:
        return None
    return datetime.fromtimestamp(int(epoch), timezone.utc).replace(tzinfo=None)
