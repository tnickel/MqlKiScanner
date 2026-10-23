"""Path-bound cleanup and conservative process-query failures, all processes fake."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from mqlkiscanner import kursdaten
from mqlkiscanner.agenten import marktdata


class Process:
    def __init__(self, pid, name, exe):
        self.pid, self._name, self._exe = pid, name, exe
        self.reads = []
    def name(self):
        self.reads.append("name")
        if isinstance(self._name, Exception):
            raise self._name
        return self._name
    def exe(self):
        self.reads.append("exe")
        if isinstance(self._exe, Exception):
            raise self._exe
        return self._exe


@pytest.fixture
def target(tmp_path, monkeypatch):
    path = str(tmp_path / "Configured" / "terminal64.exe")
    def no_os_command(*args, **kwargs):
        raise OSError("OS commands disabled in fixture")
    monkeypatch.setattr(subprocess, "run", no_os_command)
    return path


def test_psutil_reads_names_first_and_only_terminal_executables(monkeypatch, target):
    other = Process(7, "python.exe", AssertionError("Executable must not be queried"))
    matching = Process(42, "TERMINAL64.EXE", target.upper())
    foreign = Process(43, "terminal64.exe", str(Path(target).parent.parent / "Foreign" / "terminal64.exe"))
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([other, foreign, matching]))
    assert marktdata._terminal_prozesse(target) == [(42, str(Path(target).resolve()).casefold())]
    assert other.reads == ["name"]
    assert matching.reads == foreign.reads == ["name", "exe"]
    assert marktdata.terminal_laueft(target) is True


def test_resolved_path_matches_and_nearby_prefix_is_not_its_owner(monkeypatch, target):
    normalized = str(Path(target).parent / ".." / "Configured" / "terminal64.exe")
    processes = [Process(42, "terminal64.exe", normalized),
                 Process(43, "terminal64.exe", str(Path(target).parent.parent / "ConfiguredOther" / "terminal64.exe"))]
    monkeypatch.setattr(psutil, "process_iter", lambda: iter(processes))
    assert [pid for pid, _ in marktdata._terminal_prozesse(target)] == [42]


@pytest.mark.parametrize("phase", ["name", "exe"])
def test_process_disappearing_during_query_is_not_a_query_failure(monkeypatch, target, phase):
    gone = psutil.NoSuchProcess(42)
    process = Process(42, gone if phase == "name" else "terminal64.exe",
                      gone if phase == "exe" else target)
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([process]))
    assert marktdata._terminal_prozesse(target) == []
    assert marktdata.terminal_beenden(target) is True


@pytest.mark.parametrize("phase", ["name", "exe", "iteration"])
def test_access_failure_never_becomes_absent_or_successful_cleanup(monkeypatch, target, caplog, phase):
    denied = psutil.AccessDenied(42)
    process = Process(42, denied if phase == "name" else "terminal64.exe",
                      denied if phase == "exe" else target)
    def processes():
        if phase == "iteration":
            raise denied
        return iter([process])
    monkeypatch.setattr(psutil, "process_iter", processes)
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler):
        marktdata.terminal_laueft(target)
    assert marktdata.terminal_beenden(target) is False
    assert "Cleanup nicht bestätigt" in caplog.text
    assert "AccessDenied" in caplog.text


@pytest.mark.parametrize("bad_path", [None, "", "not-a-terminal.exe"])
def test_invalid_or_missing_executable_path_is_unknown(monkeypatch, target, bad_path):
    process = Process(42, "terminal64.exe", bad_path)
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([process]))
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler):
        marktdata._terminal_prozesse(target)
    assert marktdata.terminal_beenden(target) is False


def test_cim_is_used_only_if_psutil_is_unavailable(monkeypatch, target):
    monkeypatch.setitem(sys.modules, "psutil", None)
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps({"ProcessId": 42, "ExecutablePath": target}), "")
    monkeypatch.setattr(subprocess, "run", run)
    assert marktdata._terminal_prozesse(target)[0][0] == 42
    assert calls[0][0][0] == "powershell"
    assert "-ErrorAction Stop" in calls[0][0][-1]
    assert calls[0][1]["timeout"] == 20


def test_native_fallback_keeps_unicode_path_and_strict_transport(monkeypatch, target):
    unicode_target = str(Path(target).parent / "M\u00fcller \u4e2d\u6587" / "terminal64.exe")
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([Process(428, "", target)]))
    def run(command, **kwargs):
        assert "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)" in command[-1]
        assert kwargs["encoding"] == "utf-8" and kwargs["errors"] == "strict"
        return subprocess.CompletedProcess(command, 0,
            json.dumps({"ProcessId": 42, "ExecutablePath": unicode_target}, ensure_ascii=False), "")
    monkeypatch.setattr(subprocess, "run", run)
    assert marktdata._terminal_prozesse(unicode_target) == [(42, str(Path(unicode_target).resolve()).casefold())]


def test_decode_failure_is_unknown_instead_of_a_replaced_foreign_path(monkeypatch, target):
    monkeypatch.setitem(sys.modules, "psutil", None)
    def invalid_bytes(*args, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")
    monkeypatch.setattr(subprocess, "run", invalid_bytes)
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler):
        marktdata.terminal_laueft(target)
    assert marktdata.terminal_beenden(target) is False


def test_empty_security_process_name_needs_an_independent_complete_inventory(monkeypatch, target):
    unknown = Process(428, "", AssertionError("Unknown-name process path must not be queried"))
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([unknown]))
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        assert "Get-Process -ErrorAction Stop" in command[-1]
        assert "Where-Object" in command[-1]
        assert "Get-CimInstance" not in command[-1]
        return subprocess.CompletedProcess(command, 0, json.dumps([
            {"ProcessId": 42, "ExecutablePath": target},
            {"ProcessId": 43, "ExecutablePath": str(Path(target).parent.parent / "Foreign" / "terminal64.exe")},
        ]), "")
    monkeypatch.setattr(subprocess, "run", run)
    assert marktdata._terminal_prozesse(target) == [(42, str(Path(target).resolve()).casefold())]
    assert unknown.reads == ["name"]
    assert calls[0][1]["timeout"] == 5


def test_native_complete_inventory_can_prove_absence_but_not_an_unreadable_terminal(monkeypatch, target):
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([Process(428, "", target)]))
    state = {"stdout": "[]"}
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, state["stdout"], ""))
    assert marktdata._terminal_prozesse(target) == []
    state["stdout"] = json.dumps({"ProcessId": 42, "ExecutablePath": None})
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler):
        marktdata._terminal_prozesse(target)
    assert marktdata.terminal_beenden(target) is False


def test_native_path_disappearing_after_name_query_requires_explicit_post_read_exit(monkeypatch, target):
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([Process(428, "", target)]))
    def run(command, **kwargs):
        script = command[-1]
        assert script.index("$exePfad = $prozess.Path") < script.index("$beendet = $prozess.HasExited")
        return subprocess.CompletedProcess(command, 0, json.dumps({
            "ProcessId": 42, "ExecutablePath": None, "HasExited": True}), "")
    monkeypatch.setattr(subprocess, "run", run)
    assert marktdata._terminal_prozesse(target) == []
    assert marktdata.terminal_beenden(target) is True


@pytest.mark.parametrize("exit_state", [False, None, "true", 1])
def test_native_null_path_alive_or_unknown_is_still_a_cleanup_failure(monkeypatch, target, exit_state):
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([Process(428, "", target)]))
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs:
        subprocess.CompletedProcess(command, 0, json.dumps({
            "ProcessId": 42, "ExecutablePath": None, "HasExited": exit_state}), ""))
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler):
        marktdata._terminal_prozesse(target)
    assert marktdata.terminal_beenden(target) is False


def test_unknown_psutil_and_timed_out_native_query_never_report_success(monkeypatch, target):
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([Process(428, "", target)]))
    def timeout(command, **kwargs):
        assert "Get-CimInstance" not in command[-1]
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler, match="unabhängige Namensinventur"):
        marktdata.terminal_laueft(target)
    assert marktdata.terminal_beenden(target) is False


@pytest.mark.parametrize("stdout,stderr,code", [
    ("", "CIM unavailable", 1), ("[]", "nonterminating error", 0),
    ("not JSON", "", 0), ("42", "", 0),
    ('[{"ProcessId":42,"ExecutablePath":null}]', "", 0),
    ('[{"ProcessId":42}]', "", 0),
    ('[{"ProcessId":true,"ExecutablePath":"/terminal64.exe"}]', "", 0),
])
def test_cim_error_or_incomplete_schema_is_not_an_empty_process_list(monkeypatch, target, stdout, stderr, code):
    monkeypatch.setitem(sys.modules, "psutil", None)
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, code, stdout, stderr))
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler):
        marktdata._terminal_prozesse(target)
    assert marktdata.terminal_beenden(target) is False


@pytest.mark.parametrize("empty", ["", "[]", "null"])
def test_successful_empty_cim_query_is_confirmed_absence(monkeypatch, target, empty):
    monkeypatch.setitem(sys.modules, "psutil", None)
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, empty, ""))
    assert marktdata._terminal_prozesse(target) == []
    assert marktdata.terminal_beenden(target) is True


def test_original_cim_timeout_bug_cannot_report_success_or_launch_terminal(monkeypatch, target):
    monkeypatch.setitem(sys.modules, "psutil", None)
    def timeout(command, **kwargs):
        assert command[0] == "powershell"
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", timeout)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("Unknown state cannot allow a start"))
    assert marktdata.terminal_beenden(target) is False
    data = kursdaten.KursDaten({"kursdaten_terminals": [target], "markt_start_erlauben": True})
    with pytest.raises(marktdata.TerminalProzessAbfrageFehler):
        data.starten()


def test_soft_then_hard_cleanup_targets_only_confirmed_path_and_not_child_tree(monkeypatch, target):
    running = [Process(42, "terminal64.exe", target),
               Process(43, "terminal64.exe", str(Path(target).parent.parent / "Foreign" / "terminal64.exe"))]
    monkeypatch.setattr(psutil, "process_iter", lambda: iter(running))
    monkeypatch.setattr(time, "sleep", lambda _: None)
    commands = []
    def kill(command, **kwargs):
        assert command[0] == "taskkill"
        assert command[1:3] == ["/PID", "42"]
        assert "/T" not in command and "/IM" not in command
        commands.append(command)
        if "/F" in command:
            running[:] = [process for process in running if process.pid != 42]
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, "run", kill)
    assert marktdata.terminal_beenden(target) is True
    assert commands == [["taskkill", "/PID", "42"], ["taskkill", "/PID", "42", "/F"]]
    assert [process.pid for process in running] == [43]


def test_query_failure_after_soft_stop_blocks_force_and_keeps_cleanup_pending(monkeypatch, target):
    process = Process(42, "terminal64.exe", target)
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([process]))
    commands = []
    def kill(command, **kwargs):
        if command[0] == "powershell":
            return subprocess.CompletedProcess(command, 1, "", "Process path unavailable")
        commands.append(command)
        process._exe = psutil.AccessDenied(42)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, "run", kill)
    data = kursdaten.KursDaten({"kursdaten_terminals": [target]})
    data._genutzte_terminals = {"key": target}
    data.beenden()
    assert commands == [["taskkill", "/PID", "42"]]
    assert data._genutzte_terminals == {"key": target}
    # A later confirmed query may finish cleanup; the failed one was not lost.
    monkeypatch.setattr(psutil, "process_iter", lambda: iter([]))
    data.beenden()
    assert data._genutzte_terminals == {}
