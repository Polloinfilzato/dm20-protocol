#!/usr/bin/env bash
# DM20 Protocol — Interactive Installer
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/Polloinfilzato/dm20-protocol/main/install.sh)
# Or:    bash install.sh  (from the repo root)

set -euo pipefail

VERSION="0.2.0"
REPO_URL="https://github.com/Polloinfilzato/dm20-protocol.git"

# ─── Colors ────────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# ─── Helpers ───────────────────────────────────────────────────────────────────

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()    { echo -e "\n${CYAN}${BOLD}>>> $*${NC}"; }

prompt_default() {
    local prompt="$1"
    local default="$2"
    local varname="$3"
    echo -en "${prompt} ${DIM}[${default}]${NC}: "
    read -r input
    eval "$varname=\"${input:-$default}\""
}

prompt_yn() {
    local prompt="$1"
    local default="$2"  # y or n
    local varname="$3"
    if [[ "$default" == "y" ]]; then
        echo -en "${prompt} ${DIM}[Y/n]${NC}: "
    else
        echo -en "${prompt} ${DIM}[y/N]${NC}: "
    fi
    read -r input
    input="${input:-$default}"
    if [[ "${input,,}" == "y" || "${input,,}" == "yes" ]]; then
        eval "$varname=true"
    else
        eval "$varname=false"
    fi
}

prompt_choice() {
    local prompt="$1"
    shift
    local options=("$@")
    echo -e "\n${prompt}" >&2
    for i in "${!options[@]}"; do
        echo -e "  ${BOLD}$((i+1)))${NC} ${options[$i]}" >&2
    done
    echo -en "\nChoice: " >&2
    read -r choice
    echo "$choice"
}

# ─── Banner ────────────────────────────────────────────────────────────────────

banner() {
    echo -e "${CYAN}"
    cat << 'BANNER'

  ____  __  __ ____   ___
 |  _ \|  \/  |___ \ / _ \
 | | | | |\/| | __) | | | |
 | |_| | |  | |/ __/| |_| |
 |____/|_|  |_|_____|\___/
   ____            _                  _
  |  _ \ _ __ ___ | |_ ___   ___ ___|_|
  | |_) | '__/ _ \| __/ _ \ / __/ _ \| |
  |  __/| | | (_) | || (_) | (_| (_) | |
  |_|   |_|  \___/ \__\___/ \___\___/|_|

BANNER
    echo -e "${NC}"
    echo -e "  ${BOLD}DM20 Protocol${NC} v${VERSION} — Interactive Installer"
    echo -e "  ${DIM}AI-powered D&D campaign management via MCP${NC}"
    echo ""
}

# ─── Platform Detection ───────────────────────────────────────────────────────

detect_platform() {
    ARCH=$(uname -m)    # x86_64, arm64, aarch64
    OS=$(uname -s)      # Darwin, Linux

    if [[ "$OS" == "Darwin" && "$ARCH" == "x86_64" ]]; then
        PLATFORM="macos-intel"
        RAG_SUPPORTED=false
        RAG_WARNING="chromadb/onnxruntime are not available for macOS Intel (x86_64)"
    elif [[ "$OS" == "Darwin" && "$ARCH" == "arm64" ]]; then
        PLATFORM="macos-arm"
        RAG_SUPPORTED=true
        RAG_WARNING=""
    elif [[ "$OS" == "Linux" ]]; then
        PLATFORM="linux-${ARCH}"
        RAG_SUPPORTED=true
        RAG_WARNING=""
    elif [[ "$OS" == MINGW* || "$OS" == CYGWIN* || "$OS" == MSYS* ]]; then
        error "Windows is not supported by this installer."
        echo "  See the manual installation instructions in README.md"
        exit 1
    else
        PLATFORM="unknown"
        RAG_SUPPORTED=true
        RAG_WARNING=""
    fi

    info "Platform: ${BOLD}${OS} ${ARCH}${NC} (${PLATFORM})"
}

# ─── Prerequisites ─────────────────────────────────────────────────────────────

check_prerequisites() {
    step "Checking prerequisites"
    local missing=0

    # Python 3.12+
    if command -v python3 &>/dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
        PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
        if [[ "$PYTHON_MAJOR" -ge 3 && "$PYTHON_MINOR" -ge 12 ]]; then
            success "Python ${PYTHON_VERSION}"
        else
            error "Python ${PYTHON_VERSION} found, but 3.12+ required"
            echo "  Install from https://python.org or use pyenv"
            missing=1
        fi
    else
        error "Python not found"
        echo "  Install from https://python.org"
        missing=1
    fi

    # uv
    if command -v uv &>/dev/null; then
        UV_VERSION=$(uv --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        UV_PATH=$(command -v uv)
        success "uv ${UV_VERSION} (${UV_PATH})"
    else
        error "uv not found"
        echo "  Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        missing=1
    fi

    # git
    if command -v git &>/dev/null; then
        GIT_VERSION=$(git --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        success "git ${GIT_VERSION}"
    else
        error "git not found"
        if [[ "$OS" == "Darwin" ]]; then
            echo "  Install with: xcode-select --install"
        else
            echo "  Install with your package manager (apt, dnf, etc.)"
        fi
        missing=1
    fi

    if [[ "$missing" -gt 0 ]]; then
        echo ""
        error "Missing prerequisites. Install them and re-run this script."
        exit 1
    fi
}

# ─── Prompts ───────────────────────────────────────────────────────────────────

gather_options() {
    step "Configuration"

    # ── Install directory ──────────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}Where should DM20 Protocol be installed?${NC}"

    # Detect if running from inside an existing clone
    if [[ -f "pyproject.toml" ]] && grep -q 'name = "dm20-protocol"' pyproject.toml 2>/dev/null; then
        info "Detected existing clone in current directory"
        INSTALL_DIR="$(pwd)"
        CLONE_NEEDED=false
    else
        prompt_default "Install directory" "$HOME/dm20-protocol" INSTALL_DIR
        if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/pyproject.toml" ]] && grep -q 'name = "dm20-protocol"' "$INSTALL_DIR/pyproject.toml" 2>/dev/null; then
            info "Found existing clone at ${INSTALL_DIR}"
            CLONE_NEEDED=false
        else
            CLONE_NEEDED=true
        fi
    fi

    # ── MCP Client ─────────────────────────────────────────────────────────
    echo ""
    local choice
    choice=$(prompt_choice "Which MCP client(s) will you use?" \
        "Claude Desktop" \
        "Claude Code" \
        "Both")

    case "$choice" in
        1) MCP_CLIENT="desktop" ;;
        2) MCP_CLIENT="code" ;;
        3) MCP_CLIENT="both" ;;
        *) MCP_CLIENT="desktop" ;;
    esac

    # If Claude Code: global or project?
    CODE_SCOPE="global"
    if [[ "$MCP_CLIENT" == "code" || "$MCP_CLIENT" == "both" ]]; then
        echo ""
        local scope_choice
        scope_choice=$(prompt_choice "Claude Code config scope?" \
            "Global (~/.claude/mcp.json) — available in all projects" \
            "Project (.mcp.json) — only in dm20-protocol directory")

        case "$scope_choice" in
            2) CODE_SCOPE="project" ;;
            *) CODE_SCOPE="global" ;;
        esac
    fi

    # ── Data directory ─────────────────────────────────────────────────────
    echo ""
    local data_choice
    data_choice=$(prompt_choice "Where should campaign data be stored?" \
        "~/dm20-data (recommended — separate from code)" \
        "Inside the repository (${INSTALL_DIR}/data)" \
        "Custom location")

    case "$data_choice" in
        1) DATA_DIR="$HOME/dm20-data" ;;
        2) DATA_DIR="${INSTALL_DIR}/data" ;;
        3) prompt_default "Data directory" "$HOME/dm20-data" DATA_DIR ;;
        *) DATA_DIR="$HOME/dm20-data" ;;
    esac

    # ── RAG dependencies ───────────────────────────────────────────────────
    INSTALL_RAG=false
    echo ""
    if [[ "$RAG_SUPPORTED" == false ]]; then
        warn "RAG dependencies skipped: ${RAG_WARNING}"
        echo "  The server works fine without RAG. Only the 'ask_books' semantic search"
        echo "  tool requires it — all other library tools use keyword search."
    else
        echo -e "${BOLD}Install RAG dependencies?${NC}"
        echo "  Enables semantic search via 'ask_books' (~2GB download)"
        echo "  Not required — all other library tools work without it"
        prompt_yn "Install RAG dependencies?" "n" INSTALL_RAG
    fi
}

# ─── Installation ──────────────────────────────────────────────────────────────

do_clone() {
    if [[ "$CLONE_NEEDED" == true ]]; then
        step "Cloning repository"
        if [[ -d "$INSTALL_DIR" ]]; then
            warn "Directory ${INSTALL_DIR} exists but is not a dm20-protocol clone"
            prompt_yn "Remove it and clone fresh?" "n" REMOVE_DIR
            if [[ "$REMOVE_DIR" == true ]]; then
                rm -rf "$INSTALL_DIR"
            else
                error "Cannot proceed — directory exists. Choose a different location."
                exit 1
            fi
        fi
        git clone "$REPO_URL" "$INSTALL_DIR"
        success "Cloned to ${INSTALL_DIR}"
    else
        step "Updating existing clone"
        cd "$INSTALL_DIR"
        if git pull --ff-only 2>/dev/null; then
            success "Updated to latest"
        else
            warn "Could not fast-forward. You may need to manually resolve."
        fi
    fi
}

do_install_deps() {
    step "Installing dependencies"
    cd "$INSTALL_DIR"

    uv sync
    success "Core dependencies installed"

    if [[ "$INSTALL_RAG" == true ]]; then
        info "Installing RAG dependencies (this may take a few minutes)..."
        if uv sync --extra rag; then
            success "RAG dependencies installed"
        else
            warn "RAG installation failed. The server will work without RAG."
            warn "You can try again later with: cd ${INSTALL_DIR} && uv sync --extra rag"
        fi
    fi
}

do_create_data_dirs() {
    step "Setting up data directory"
    mkdir -p "${DATA_DIR}/campaigns"
    mkdir -p "${DATA_DIR}/library/pdfs"
    mkdir -p "${DATA_DIR}/library/index"
    mkdir -p "${DATA_DIR}/library/extracted"
    success "Data directory created at ${DATA_DIR}"
}

do_write_env() {
    step "Writing .env file"
    local env_file="${INSTALL_DIR}/.env"

    if [[ -f "$env_file" ]]; then
        local backup="${env_file}.backup.$(date +%Y%m%d%H%M%S)"
        cp "$env_file" "$backup"
        info "Backed up existing .env to ${backup}"
    fi

    cat > "$env_file" << EOF
DM20_STORAGE_DIR=${DATA_DIR}
EOF
    success ".env written"
}

# ─── MCP Client Configuration ─────────────────────────────────────────────────

update_json_config() {
    local config_file="$1"
    local use_abs_uv="$2"    # true for Desktop, false for Code
    local add_type="$3"      # true for Code, false for Desktop

    # Build the new server entry using Python (no jq dependency)
    python3 << PYEOF
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

config_file = "$config_file"
install_dir = "$INSTALL_DIR"
data_dir = "$DATA_DIR"
use_abs_uv = "$use_abs_uv" == "true"
add_type = "$add_type" == "true"

# Resolve uv path
if use_abs_uv:
    uv_cmd = "$UV_PATH"
else:
    uv_cmd = "uv"

# Build new server entry
server_entry = {}
if add_type:
    server_entry["type"] = "stdio"
server_entry["command"] = uv_cmd
server_entry["args"] = ["run", "python", "-m", "dm20_protocol"]
server_entry["cwd"] = install_dir
server_entry["env"] = {
    "DM20_STORAGE_DIR": data_dir
}

# Read existing config or create new
config_path = Path(config_file)
if config_path.exists():
    # Create backup
    backup = config_path.with_suffix(f".backup.{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
    shutil.copy2(config_file, backup)
    print(f"  Backed up to {backup}")

    with open(config_file) as f:
        config = json.load(f)
else:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {}

# Merge
if "mcpServers" not in config:
    config["mcpServers"] = {}

config["mcpServers"]["dm20-protocol"] = server_entry

# Write
with open(config_file, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print(f"  Updated {config_file}")
PYEOF
}

do_configure_mcp() {
    step "Configuring MCP client(s)"

    # Claude Desktop
    if [[ "$MCP_CLIENT" == "desktop" || "$MCP_CLIENT" == "both" ]]; then
        local desktop_config
        if [[ "$OS" == "Darwin" ]]; then
            desktop_config="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
        else
            desktop_config="$HOME/.config/Claude/claude_desktop_config.json"
        fi
        info "Configuring Claude Desktop..."
        update_json_config "$desktop_config" true false
        success "Claude Desktop configured"
    fi

    # Claude Code
    if [[ "$MCP_CLIENT" == "code" || "$MCP_CLIENT" == "both" ]]; then
        local code_config
        if [[ "$CODE_SCOPE" == "global" ]]; then
            code_config="$HOME/.claude/mcp.json"
        else
            code_config="${INSTALL_DIR}/.mcp.json"
        fi
        info "Configuring Claude Code (${CODE_SCOPE})..."
        update_json_config "$code_config" false true
        success "Claude Code configured (${CODE_SCOPE})"
    fi
}

# ─── Verification ──────────────────────────────────────────────────────────────

do_verify() {
    step "Verifying installation"
    cd "$INSTALL_DIR"

    # Smoke test: import the package
    if uv run python3 -c "from dm20_protocol.main import main; print('Import OK')" 2>/dev/null; then
        success "Server module loads correctly"
    else
        warn "Server module failed to load. Check the output above for errors."
    fi
}

# ─── Summary ───────────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}${BOLD}  Installation complete!${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  ${BOLD}Install dir:${NC}  ${INSTALL_DIR}"
    echo -e "  ${BOLD}Data dir:${NC}     ${DATA_DIR}"
    echo -e "  ${BOLD}Platform:${NC}     ${PLATFORM}"
    echo -e "  ${BOLD}RAG:${NC}          $([ "$INSTALL_RAG" == true ] && echo "Installed" || echo "Skipped")"
    echo -e "  ${BOLD}MCP client:${NC}   ${MCP_CLIENT}"
    echo ""

    if [[ "$MCP_CLIENT" == "desktop" || "$MCP_CLIENT" == "both" ]]; then
        echo -e "  ${BOLD}Next step (Claude Desktop):${NC}"
        echo "    Restart Claude Desktop to pick up the new MCP server."
        echo ""
    fi

    if [[ "$MCP_CLIENT" == "code" || "$MCP_CLIENT" == "both" ]]; then
        echo -e "  ${BOLD}Next step (Claude Code):${NC}"
        echo "    Run /mcp in Claude Code to verify the connection."
        echo ""
    fi

    echo -e "  ${BOLD}Run manually:${NC}"
    echo "    cd ${INSTALL_DIR} && uv run python -m dm20_protocol"
    echo ""
    echo -e "  ${BOLD}Add PDF rulebooks:${NC}"
    echo "    Drop .pdf or .md files into: ${DATA_DIR}/library/pdfs/"
    echo ""
    echo -e "  ${DIM}Documentation: https://github.com/Polloinfilzato/dm20-protocol${NC}"
    echo ""
}

# ─── Main ──────────────────────────────────────────────────────────────────────

main() {
    banner
    detect_platform
    check_prerequisites
    gather_options
    do_clone
    do_install_deps
    do_create_data_dirs
    do_write_env
    do_configure_mcp
    do_verify
    print_summary
}

main "$@"
