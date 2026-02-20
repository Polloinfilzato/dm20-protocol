"""macOS Application Firewall helper for Party Mode.

Ensures the current Python executable is authorized to accept incoming
connections so that phones on the LAN can reach the Party Mode server.
"""

import logging
import platform
import subprocess
import sys

logger = logging.getLogger(__name__)

SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"


def ensure_firewall_allows_python() -> str:
    """Check and authorize the current Python in the macOS Application Firewall.

    Returns a status string:
      - "not_macos"            – skipped, not running on macOS
      - "firewall_disabled"    – firewall is off, nothing to do
      - "already_authorized"   – Python is already allowed
      - "authorized"           – Python was just added and unblocked
      - "needs_sudo: <cmd>"    – privilege escalation required; includes the command to run
      - "error: <details>"     – unexpected failure (non-fatal)
    """
    if platform.system() != "Darwin":
        return "not_macos"

    python_path = sys.executable

    try:
        # Check if firewall is enabled at all
        fw_state = subprocess.run(
            [SOCKETFILTERFW, "--getglobalstate"],
            capture_output=True, text=True, timeout=5,
        )
        if "disabled" in fw_state.stdout.lower():
            return "firewall_disabled"

        # Check if Python is already authorized
        result = subprocess.run(
            [SOCKETFILTERFW, "--getappblocked", python_path],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.lower()

        # If the app is already permitted (not blocked), we're good
        if "permitted" in output or ("block" in output and "not" in output):
            return "already_authorized"

        # Try to add and unblock Python (requires root)
        add_result = subprocess.run(
            [SOCKETFILTERFW, "--add", python_path],
            capture_output=True, text=True, timeout=5,
        )
        unblock_result = subprocess.run(
            [SOCKETFILTERFW, "--unblockapp", python_path],
            capture_output=True, text=True, timeout=5,
        )

        # Check if the commands succeeded
        if add_result.returncode == 0 and unblock_result.returncode == 0:
            return "authorized"

        # Permission denied — build the manual command for the user
        sudo_cmd = (
            f"sudo {SOCKETFILTERFW} --add {python_path} && "
            f"sudo {SOCKETFILTERFW} --unblockapp {python_path}"
        )
        return f"needs_sudo: {sudo_cmd}"

    except FileNotFoundError:
        return "error: socketfilterfw not found — is the Application Firewall installed?"
    except subprocess.TimeoutExpired:
        return "error: firewall check timed out"
    except Exception as exc:
        logger.debug("Firewall check failed: %s", exc)
        return f"error: {exc}"


def format_firewall_status(status: str) -> str:
    """Return a human-readable message for the firewall check result."""
    if status == "not_macos":
        return ""
    if status == "firewall_disabled":
        return ""
    if status == "already_authorized":
        return "Firewall: Python is already authorized for incoming connections."
    if status == "authorized":
        return "Firewall: Python has been authorized for incoming connections."
    if status.startswith("needs_sudo:"):
        cmd = status.removeprefix("needs_sudo: ")
        return (
            "**Firewall: Python is NOT authorized for incoming connections.**\n"
            "Players on your network will not be able to connect until you run:\n"
            f"```\n{cmd}\n```\n"
            "Then restart Party Mode."
        )
    if status.startswith("error:"):
        detail = status.removeprefix("error: ")
        return f"Firewall check skipped ({detail})."
    return ""
