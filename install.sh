#!/usr/bin/env bash
# DM20 Protocol — Interactive Installer
# Usage: bash <(curl -fsSL https://raw.githubusercontent.com/Polloinfilzato/dm20-protocol/main/install.sh)
# Or:    bash install.sh  (from the repo root)

set -euo pipefail

VERSION="0.3.0"
REPO_URL="https://github.com/Polloinfilzato/dm20-protocol.git"

# ─── Global State ─────────────────────────────────────────────────────────────

INSTALL_MODE=""          # "user" or "developer"
INSIDE_CLONE=false       # true when running from inside an existing clone
INSTALL_DIR=""           # developer mode: repo directory
PLAY_DIR=""              # user mode: play directory
DATA_DIR=""              # both modes: campaign data directory
CLONE_NEEDED=false       # developer mode: whether to git clone
MCP_CLIENT=""            # "desktop", "code", or "both"
CODE_SCOPE="global"      # "global" or "project"
INSTALL_RAG=false        # whether to install RAG extras
DM20_BINARY_PATH=""      # user mode: resolved path to dm20-protocol binary
ON_ICLOUD=false          # true if target dir is on iCloud Drive
MODEL_PROFILE="balanced" # model quality profile: quality, balanced, economy

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
    printf -v "$varname" '%s' "${input:-$default}"
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

# Reject system paths where a git clone would be dangerous or nonsensical
validate_install_path() {
    local dir="$1"

    # Normalize: strip trailing slashes, resolve ~ to $HOME
    dir="${dir%/}"
    dir="${dir/#\~/$HOME}"

    case "$dir" in
        /|/usr|/usr/local|/bin|/sbin|/etc|/var|/tmp|/opt|/System|/Library|/private)
            error "Cannot install to system directory: ${dir}"
            exit 1
            ;;
        "$HOME")
            error "Cannot install directly into your home directory."
            echo "  Try: ${HOME}/dm20-protocol"
            exit 1
            ;;
    esac
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
        RAG_SUPPORTED=true
        RAG_WARNING=""
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

# ─── Mode Detection ──────────────────────────────────────────────────────────

detect_mode() {
    step "Detecting install mode"

    # If running from inside an existing clone → auto-set developer
    if [[ -f "pyproject.toml" ]] && grep -q 'name = "dm20-protocol"' pyproject.toml 2>/dev/null; then
        INSIDE_CLONE=true
        INSTALL_MODE="developer"
        info "Running from inside a dm20-protocol clone — Developer mode selected"
        return
    fi

    echo ""
    echo -e "${BOLD}How do you want to install DM20 Protocol?${NC}"
    echo ""
    local choice
    choice=$(prompt_choice "Choose installation mode:" \
        "User (recommended) — just play D&D, minimal footprint" \
        "Developer — full source code for contributors")

    case "$choice" in
        1) INSTALL_MODE="user" ;;
        2) INSTALL_MODE="developer" ;;
        *) INSTALL_MODE="user" ;;
    esac

    info "Install mode: ${BOLD}${INSTALL_MODE}${NC}"
}

# ─── iCloud Detection ─────────────────────────────────────────────────────────

detect_icloud() {
    local check_dir
    if [[ "$INSTALL_MODE" == "user" ]]; then
        check_dir="$PLAY_DIR"
    else
        check_dir="$INSTALL_DIR"
    fi

    # Check if target dir is inside iCloud Drive
    local resolved_dir
    resolved_dir=$(cd "$check_dir" 2>/dev/null && pwd -P || echo "$check_dir")

    if [[ "$resolved_dir" == *"com~apple~CloudDocs"* ]] || \
       [[ "$resolved_dir" == *"Mobile Documents"* ]]; then
        ON_ICLOUD=true
    elif [[ "$OS" == "Darwin" ]]; then
        # Check if Desktop or Documents are iCloud-synced
        local real_desktop real_documents
        real_desktop=$(cd "$HOME/Desktop" 2>/dev/null && pwd -P 2>/dev/null || echo "")
        real_documents=$(cd "$HOME/Documents" 2>/dev/null && pwd -P 2>/dev/null || echo "")

        if [[ -n "$real_desktop" && "$real_desktop" == *"com~apple~CloudDocs"* && \
              "$resolved_dir" == "$HOME/Desktop"* ]]; then
            ON_ICLOUD=true
        elif [[ -n "$real_documents" && "$real_documents" == *"com~apple~CloudDocs"* && \
                "$resolved_dir" == "$HOME/Documents"* ]]; then
            ON_ICLOUD=true
        fi
    fi

    if [[ "$ON_ICLOUD" == true ]]; then
        warn "Install directory is on iCloud Drive"
        if [[ "$INSTALL_MODE" == "developer" ]]; then
            info "Will protect .venv from iCloud sync (via .nosync + symlink)"
        else
            info "Data files will sync via iCloud (this is fine for campaign data)"
        fi
    fi
}

setup_venv_nosync() {
    # Create .venv.nosync + symlink so iCloud doesn't set UF_HIDDEN on venv files.
    # This prevents Python from skipping .pth files (editable installs).
    # See: https://github.com/pypa/setuptools/issues/4595
    local venv_link="${INSTALL_DIR}/.venv"
    local venv_real="${INSTALL_DIR}/.venv.nosync"

    # Already set up correctly
    if [[ -L "$venv_link" && -d "$venv_real" ]]; then
        success "iCloud protection already in place (.venv → .venv.nosync)"
        return 0
    fi

    # Existing .venv is a real directory — iCloud has been tainting it.
    # We must delete and recreate from scratch so iCloud never indexes the new files.
    # A simple move would preserve iCloud's hidden flags.
    if [[ -d "$venv_link" && ! -L "$venv_link" ]]; then
        info "Removing iCloud-tainted .venv (will be recreated by uv sync)..."
        rm -rf "$venv_link"
    fi

    # Create the nosync directory and symlink
    mkdir -p "$venv_real"
    ln -sf ".venv.nosync" "$venv_link"
    success "iCloud protection: .venv → .venv.nosync (iCloud will ignore it)"
}

# ─── Auto-install Helpers ─────────────────────────────────────────────────────

install_homebrew() {
    info "Installing Homebrew..."
    if /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; then
        # Make brew available in the current session
        if [[ -x "/opt/homebrew/bin/brew" ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -x "/usr/local/bin/brew" ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        if command -v brew &>/dev/null; then
            HAS_BREW=true
            success "Homebrew installed successfully"
            return 0
        else
            error "Homebrew was installed but not found in PATH"
            return 1
        fi
    else
        error "Failed to install Homebrew"
        return 1
    fi
}

install_uv() {
    if [[ "$OS" == "Darwin" && "$HAS_BREW" == true ]]; then
        info "Installing uv via Homebrew..."
        if brew install uv; then
            success "uv installed via Homebrew"
            return 0
        else
            error "Failed to install uv via Homebrew"
            return 1
        fi
    else
        info "Installing uv via official installer..."
        if curl -LsSf https://astral.sh/uv/install.sh | sh; then
            # Make uv available in the current session
            export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
            if command -v uv &>/dev/null; then
                success "uv installed successfully"
                return 0
            else
                error "uv was installed but not found in PATH"
                return 1
            fi
        else
            error "Failed to install uv"
            return 1
        fi
    fi
}

install_python() {
    info "Installing Python 3.12 via uv..."
    if uv python install 3.12; then
        success "Python 3.12 installed via uv"
        return 0
    else
        error "Failed to install Python 3.12"
        return 1
    fi
}

install_git() {
    if [[ "$OS" == "Darwin" && "$HAS_BREW" == true ]]; then
        info "Installing git via Homebrew..."
        if brew install git; then
            success "git installed via Homebrew"
            return 0
        else
            error "Failed to install git via Homebrew"
            return 1
        fi
    elif [[ "$OS" == "Darwin" ]]; then
        info "Installing git via Xcode Command Line Tools..."
        xcode-select --install 2>/dev/null || true
        echo ""
        echo -en "  Press ${BOLD}Enter${NC} when Xcode CLI tools installation is complete... "
        read -r
        if command -v git &>/dev/null; then
            return 0
        else
            error "git still not found after Xcode CLI tools install"
            return 1
        fi
    elif command -v apt-get &>/dev/null; then
        info "Installing git via apt..."
        sudo apt-get update && sudo apt-get install -y git
    elif command -v dnf &>/dev/null; then
        info "Installing git via dnf..."
        sudo dnf install -y git
    elif command -v pacman &>/dev/null; then
        info "Installing git via pacman..."
        sudo pacman -S --noconfirm git
    elif command -v zypper &>/dev/null; then
        info "Installing git via zypper..."
        sudo zypper install -y git
    elif command -v apk &>/dev/null; then
        info "Installing git via apk..."
        sudo apk add git
    else
        error "Cannot auto-install git on this system"
        echo "  Install git manually, then re-run this script"
        return 1
    fi
}

# ─── Prerequisites ─────────────────────────────────────────────────────────────

check_prerequisites() {
    step "Checking prerequisites"
    local missing=0

    # ── Homebrew (macOS only) ──────────────────────────────────────────────
    HAS_BREW=false
    if [[ "$OS" == "Darwin" ]]; then
        if command -v brew &>/dev/null; then
            HAS_BREW=true
            local brew_ver
            brew_ver=$(brew --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")
            success "Homebrew ${brew_ver}"
        else
            warn "Homebrew not found"
            echo ""
            echo -e "  ${BOLD}Homebrew${NC} is the standard package manager for macOS."
            echo "  It makes installing and updating developer tools effortless."
            echo -e "  ${DIM}https://brew.sh${NC}"
            echo ""
            prompt_yn "  Install Homebrew now?" "y" INSTALL_BREW
            if [[ "$INSTALL_BREW" == true ]]; then
                if install_homebrew; then
                    : # success already printed by install_homebrew
                else
                    info "Continuing without Homebrew (using alternative installers)"
                fi
            else
                info "Skipping Homebrew (will use alternative installers)"
            fi
        fi
    fi

    # ── uv (always needed — both modes) ──────────────────────────────────
    if command -v uv &>/dev/null; then
        UV_VERSION=$(uv --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        UV_PATH=$(command -v uv)
        success "uv ${UV_VERSION} (${UV_PATH})"
    else
        warn "uv not found"
        local uv_method="official installer"
        [[ "$OS" == "Darwin" && "$HAS_BREW" == true ]] && uv_method="Homebrew"
        prompt_yn "  Install uv now? (via ${uv_method})" "y" INSTALL_UV
        if [[ "$INSTALL_UV" == true ]]; then
            if install_uv; then
                UV_VERSION=$(uv --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
                UV_PATH=$(command -v uv)
                success "uv ${UV_VERSION} (${UV_PATH})"
            else
                echo "  Manual install: curl -LsSf https://astral.sh/uv/install.sh | sh"
                missing=1
            fi
        else
            echo "  Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
            missing=1
        fi
    fi

    # ── Python 3.12+ (developer mode only) ────────────────────────────────
    if [[ "$INSTALL_MODE" == "developer" ]]; then
        local python_ok=false
        if command -v python3 &>/dev/null; then
            PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
            PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
            PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
            if [[ "$PYTHON_MAJOR" -ge 3 && "$PYTHON_MINOR" -ge 12 ]]; then
                success "Python ${PYTHON_VERSION}"
                python_ok=true
            fi
        fi

        if [[ "$python_ok" == false ]]; then
            if [[ -n "${PYTHON_VERSION:-}" ]]; then
                warn "Python ${PYTHON_VERSION} found, but 3.12+ required"
            else
                warn "Python not found"
            fi

            # Can only auto-install if uv is available
            if command -v uv &>/dev/null; then
                prompt_yn "  Install Python 3.12 via uv?" "y" INSTALL_PYTHON
                if [[ "$INSTALL_PYTHON" == true ]]; then
                    if install_python; then
                        success "Python 3.12 available (managed by uv)"
                    else
                        echo "  Install from https://python.org or use pyenv"
                        missing=1
                    fi
                else
                    echo "  Install from https://python.org or use pyenv"
                    missing=1
                fi
            else
                echo "  Install from https://python.org or use pyenv"
                echo "  (uv could install Python for you, but uv is not available)"
                missing=1
            fi
        fi
    fi

    # ── git (developer mode only) ─────────────────────────────────────────
    if [[ "$INSTALL_MODE" == "developer" ]]; then
        if command -v git &>/dev/null; then
            GIT_VERSION=$(git --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            success "git ${GIT_VERSION}"
        else
            warn "git not found"
            prompt_yn "  Install git now?" "y" INSTALL_GIT
            if [[ "$INSTALL_GIT" == true ]]; then
                if install_git; then
                    GIT_VERSION=$(git --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
                    success "git ${GIT_VERSION}"
                else
                    if [[ "$OS" == "Darwin" ]]; then
                        echo "  Install with: xcode-select --install"
                    else
                        echo "  Install with your package manager (apt, dnf, etc.)"
                    fi
                    missing=1
                fi
            else
                if [[ "$OS" == "Darwin" ]]; then
                    echo "  Install with: xcode-select --install"
                else
                    echo "  Install with your package manager (apt, dnf, etc.)"
                fi
                missing=1
            fi
        fi
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

    if [[ "$INSTALL_MODE" == "user" ]]; then
        gather_options_user
    else
        gather_options_developer
    fi
}

gather_options_user() {
    # ── Play directory ────────────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}Where should DM20 set up your play directory?${NC}"
    echo -e "  ${DIM}This is where config and campaign data will live${NC}"
    prompt_default "Play directory" "$HOME/dm20" PLAY_DIR
    PLAY_DIR="${PLAY_DIR/#\~/$HOME}"

    # Ensure PLAY_DIR is an absolute path
    if [[ ! "$PLAY_DIR" == /* ]]; then
        PLAY_DIR="$(pwd)/${PLAY_DIR}"
    fi

    # Validate the path is reasonable
    if [[ -z "$PLAY_DIR" || ${#PLAY_DIR} -lt 3 ]]; then
        error "Invalid play directory: '${PLAY_DIR}'"
        exit 1
    fi

    DATA_DIR="${PLAY_DIR}/data"

    # ── MCP Client ────────────────────────────────────────────────────────
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
    CODE_SCOPE="project"  # always project-scoped in user mode

    # ── Model Quality Profile ─────────────────────────────────────────────
    echo ""
    local profile_choice
    profile_choice=$(prompt_choice "Model quality profile:" \
        "Balanced — Sonnet models, good quality [recommended]" \
        "Quality — Opus models, best narrative (uses more tokens)" \
        "Economy — Haiku models, fast and cheap (great for Pro plan)")
    case "$profile_choice" in
        2) MODEL_PROFILE="quality" ;;
        3) MODEL_PROFILE="economy" ;;
        *) MODEL_PROFILE="balanced" ;;
    esac

    # ── RAG dependencies ──────────────────────────────────────────────────
    INSTALL_RAG=false
    echo ""
    if [[ "$RAG_SUPPORTED" == false ]]; then
        warn "RAG dependencies skipped: ${RAG_WARNING}"
        echo "  The server works fine without RAG. The Claudmaster AI DM uses it for"
        echo "  module indexing — all other tools (including ask_books) work without it."
    else
        echo -e "${BOLD}Install RAG dependencies?${NC}"
        echo "  Enables vector search for Claudmaster AI DM module indexing (~2GB download)"
        echo "  Not required — all tools including ask_books work without it"
        prompt_yn "Install RAG dependencies?" "n" INSTALL_RAG
    fi
}

gather_options_developer() {
    # ── Install directory ──────────────────────────────────────────────────
    echo ""
    echo -e "${BOLD}Where should DM20 Protocol be installed?${NC}"

    if [[ "$INSIDE_CLONE" == true ]]; then
        INSTALL_DIR="$(pwd)"
        CLONE_NEEDED=false
        info "Using current directory: ${INSTALL_DIR}"
    else
        echo -e "  ${DIM}A dm20-protocol/ directory will be created inside your choice${NC}"
        local parent_dir
        prompt_default "Parent directory" "$HOME" parent_dir
        parent_dir="${parent_dir/#\~/$HOME}"
        parent_dir="${parent_dir%/}"
        INSTALL_DIR="${parent_dir}/dm20-protocol"

        if [[ -d "$INSTALL_DIR" && -f "$INSTALL_DIR/pyproject.toml" ]] && \
           grep -q 'name = "dm20-protocol"' "$INSTALL_DIR/pyproject.toml" 2>/dev/null; then
            info "Found existing clone at ${INSTALL_DIR}"
            CLONE_NEEDED=false
        else
            CLONE_NEEDED=true
        fi
        validate_install_path "$INSTALL_DIR"
    fi

    # ── MCP Client ────────────────────────────────────────────────────────
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

    # ── Data directory ────────────────────────────────────────────────────
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

    # ── Model Quality Profile ─────────────────────────────────────────────
    echo ""
    local profile_choice
    profile_choice=$(prompt_choice "Model quality profile:" \
        "Balanced — Sonnet models, good quality [recommended]" \
        "Quality — Opus models, best narrative (uses more tokens)" \
        "Economy — Haiku models, fast and cheap (great for Pro plan)")
    case "$profile_choice" in
        2) MODEL_PROFILE="quality" ;;
        3) MODEL_PROFILE="economy" ;;
        *) MODEL_PROFILE="balanced" ;;
    esac

    # ── RAG dependencies ──────────────────────────────────────────────────
    INSTALL_RAG=false
    echo ""
    if [[ "$RAG_SUPPORTED" == false ]]; then
        warn "RAG dependencies skipped: ${RAG_WARNING}"
        echo "  The server works fine without RAG. The Claudmaster AI DM uses it for"
        echo "  module indexing — all other tools (including ask_books) work without it."
    else
        echo -e "${BOLD}Install RAG dependencies?${NC}"
        echo "  Enables vector search for Claudmaster AI DM module indexing (~2GB download)"
        echo "  Not required — all tools including ask_books work without it"
        prompt_yn "Install RAG dependencies?" "n" INSTALL_RAG
    fi
}

# ─── Installation (User mode) ─────────────────────────────────────────────────

do_tool_install() {
    step "Installing dm20-protocol"

    local pkg_spec="dm20-protocol"
    if [[ "$INSTALL_RAG" == true ]]; then
        pkg_spec="dm20-protocol[rag]"
    fi

    info "Running: uv tool install \"${pkg_spec} @ git+${REPO_URL}\" --force"
    if uv tool install "${pkg_spec} @ git+${REPO_URL}" --force; then
        success "dm20-protocol installed"
    else
        error "Installation failed"
        exit 1
    fi

    # Resolve the binary path (needed for MCP config)
    if command -v dm20-protocol &>/dev/null; then
        DM20_BINARY_PATH=$(command -v dm20-protocol)
    elif [[ -x "$HOME/.local/bin/dm20-protocol" ]]; then
        DM20_BINARY_PATH="$HOME/.local/bin/dm20-protocol"
        warn "dm20-protocol not in PATH — adding \$HOME/.local/bin to your shell profile"
        warn "is recommended but not required (MCP config uses the absolute path)."
    else
        error "dm20-protocol binary not found after installation"
        exit 1
    fi
}

do_create_play_dir() {
    step "Setting up play directory at ${PLAY_DIR}"

    # Create the base directory first with explicit error handling
    if ! mkdir -p "${PLAY_DIR}" 2>/dev/null; then
        error "Cannot create play directory: ${PLAY_DIR}"
        error "Check that the parent directory exists and is writable."
        exit 1
    fi

    mkdir -p "${PLAY_DIR}/data/campaigns"
    mkdir -p "${PLAY_DIR}/data/library/pdfs"
    mkdir -p "${PLAY_DIR}/data/library/index"
    mkdir -p "${PLAY_DIR}/data/library/extracted"
    mkdir -p "${PLAY_DIR}/.claude/agents"

    # Copy agent template files from the installed package into the play dir
    # so that /dm:profile can modify them at runtime
    info "Copying CC agent templates to play directory..."
    local agents_src
    agents_src=$(python3 -c "
import importlib.resources as pkg_resources
try:
    # dm20-protocol ships agent templates in the package data
    import dm20_protocol
    import os
    pkg_dir = os.path.dirname(dm20_protocol.__file__)
    # Walk up to find .claude/agents/ in the installed tree
    base = pkg_dir
    for _ in range(5):
        candidate = os.path.join(base, '.claude', 'agents')
        if os.path.isdir(candidate):
            print(candidate)
            break
        base = os.path.dirname(base)
except Exception:
    pass
" 2>/dev/null)

    if [[ -n "$agents_src" && -d "$agents_src" ]]; then
        cp -n "$agents_src"/*.md "${PLAY_DIR}/.claude/agents/" 2>/dev/null || true
        success "Agent templates copied to ${PLAY_DIR}/.claude/agents/"
    else
        # Fallback: create minimal agent files from scratch
        for agent_file in narrator.md combat-handler.md rules-lookup.md; do
            local target="${PLAY_DIR}/.claude/agents/${agent_file}"
            if [[ ! -f "$target" ]]; then
                local agent_name="${agent_file%.md}"
                local model="sonnet"
                [[ "$agent_name" == "rules-lookup" ]] && model="haiku"
                cat > "$target" << AGENTEOF
---
name: ${agent_name}
model: ${model}
---
AGENTEOF
            fi
        done
        success "Minimal agent templates created in ${PLAY_DIR}/.claude/agents/"
    fi
}

# ─── Installation (Developer mode) ────────────────────────────────────────────

do_clone() {
    if [[ "$CLONE_NEEDED" == true ]]; then
        step "Cloning repository"
        if [[ -d "$INSTALL_DIR" ]]; then
            error "Directory ${INSTALL_DIR} already exists but is not a dm20-protocol clone."
            echo "  Remove it or choose a different parent directory and re-run."
            exit 1
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

    # Protect .venv from iCloud before creating it
    if [[ "$ON_ICLOUD" == true ]]; then
        setup_venv_nosync
    fi

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
install_mode = "$INSTALL_MODE"
use_abs_uv = "$use_abs_uv" == "true"
add_type = "$add_type" == "true"
on_icloud = "$ON_ICLOUD" == "true"
model_profile = "$MODEL_PROFILE"

server_entry = {}

if install_mode == "user":
    data_dir = "$DATA_DIR"
    play_dir = "$PLAY_DIR"
    binary_path = "${DM20_BINARY_PATH}"

    if add_type:
        # Claude Code — uses plain command name
        server_entry["type"] = "stdio"
        server_entry["command"] = "dm20-protocol"
    else:
        # Claude Desktop — needs absolute path (no user PATH)
        server_entry["command"] = binary_path if binary_path else "dm20-protocol"

    env = {"DM20_STORAGE_DIR": data_dir}
    # Point to play dir's .claude/agents/ for profile switching
    agents_dir = str(Path(play_dir) / ".claude" / "agents")
    env["DM20_AGENTS_DIR"] = agents_dir
    env["DM20_DEFAULT_PROFILE"] = model_profile
    server_entry["env"] = env

else:
    install_dir = "${INSTALL_DIR}"
    data_dir = "$DATA_DIR"

    # Resolve uv path
    if use_abs_uv:
        uv_cmd = "${UV_PATH:-uv}"
    else:
        uv_cmd = "uv"

    if add_type:
        # Claude Code supports "cwd" field
        server_entry["type"] = "stdio"
        server_entry["command"] = uv_cmd
        server_entry["args"] = ["run", "python", "-m", "dm20_protocol"]
        server_entry["cwd"] = install_dir
    else:
        # Claude Desktop does NOT support "cwd" — use --directory flag instead
        server_entry["command"] = uv_cmd
        server_entry["args"] = ["run", "--directory", install_dir, "python", "-m", "dm20_protocol"]

    env = {"DM20_STORAGE_DIR": data_dir}
    # Developer mode: agents live in repo's .claude/agents/
    env["DM20_AGENTS_DIR"] = str(Path(install_dir) / ".claude" / "agents")
    env["DM20_DEFAULT_PROFILE"] = model_profile
    # Safety net: if on iCloud, add PYTHONPATH to bypass hidden .pth files
    if on_icloud:
        env["PYTHONPATH"] = str(Path(install_dir) / "src")
    server_entry["env"] = env

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
        if [[ "$INSTALL_MODE" == "user" ]]; then
            code_config="${PLAY_DIR}/.mcp.json"
        elif [[ "$CODE_SCOPE" == "global" ]]; then
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

    if [[ "$INSTALL_MODE" == "user" ]]; then
        if command -v dm20-protocol &>/dev/null || [[ -x "${DM20_BINARY_PATH}" ]]; then
            success "MCP server ready"
        else
            warn "dm20-protocol binary not found — MCP config may not work"
        fi
    else
        cd "$INSTALL_DIR"
        # Smoke test: import the package
        if uv run python3 -c "from dm20_protocol.main import main; print('Import OK')" 2>/dev/null; then
            success "Server module loads correctly"
        else
            warn "Server module failed to load. Check the output above for errors."
        fi
    fi
}

# ─── Summary ───────────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}${BOLD}  Installation complete!${NC}"
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    if [[ "$INSTALL_MODE" == "user" ]]; then
        print_summary_user
    else
        print_summary_developer
    fi
}

print_summary_user() {
    echo -e "  ${BOLD}Mode:${NC}         User"
    echo -e "  ${BOLD}Play dir:${NC}     ${PLAY_DIR}"
    echo -e "  ${BOLD}Data dir:${NC}     ${DATA_DIR}"
    echo -e "  ${BOLD}Platform:${NC}     ${PLATFORM}"
    echo -e "  ${BOLD}Profile:${NC}      ${MODEL_PROFILE}"
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
        echo "    cd ${PLAY_DIR} && claude"
        echo "    Then run /mcp to verify the connection."
        echo ""
    fi

    echo -e "  ${BOLD}Add PDF rulebooks:${NC}"
    echo "    Drop .pdf or .md files into: ${DATA_DIR}/library/pdfs/"
    echo ""
    echo -e "  ${BOLD}Update later:${NC}"
    echo "    uv tool upgrade dm20-protocol"
    echo ""
    echo -e "  ${DIM}Documentation: https://github.com/Polloinfilzato/dm20-protocol${NC}"
    echo ""
}

print_summary_developer() {
    echo -e "  ${BOLD}Mode:${NC}         Developer"
    echo -e "  ${BOLD}Install dir:${NC}  ${INSTALL_DIR}"
    echo -e "  ${BOLD}Data dir:${NC}     ${DATA_DIR}"
    echo -e "  ${BOLD}Platform:${NC}     ${PLATFORM}"
    echo -e "  ${BOLD}Profile:${NC}      ${MODEL_PROFILE}"
    echo -e "  ${BOLD}RAG:${NC}          $([ "$INSTALL_RAG" == true ] && echo "Installed" || echo "Skipped")"
    echo -e "  ${BOLD}MCP client:${NC}   ${MCP_CLIENT}"
    if [[ "$ON_ICLOUD" == true ]]; then
        echo -e "  ${BOLD}iCloud:${NC}       Protected (.venv.nosync + PYTHONPATH)"
    fi
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
    detect_mode
    check_prerequisites
    gather_options

    if [[ "$INSTALL_MODE" == "user" ]]; then
        do_tool_install
        do_create_play_dir
        detect_icloud
        do_configure_mcp
        do_verify
    else
        do_clone
        detect_icloud
        do_install_deps
        do_create_data_dirs
        do_write_env
        do_configure_mcp
        do_verify
    fi

    print_summary
}

main "$@"
