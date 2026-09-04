"""MQL5-Zugriffsschicht (Phase 0/1, doc/04_roadmap.md).

Alle HTTP-Zugriffe laufen ueber Mql5Session mit eingebautem Rate-Limiter —
automatisiertes, zu schnelles Abrufen kann gegen MQL5-ToS verstossen und
zur Accountsperrfuehren (AGENTS.md Technik-Hinweis 6). Format-Details:
doc/02_technik-mql5.md.
"""
