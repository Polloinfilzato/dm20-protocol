---
description: Install RAG dependencies (ChromaDB + sentence-transformers) for vector search
allowed-tools: Bash
---

# Install RAG Dependencies

Install optional RAG dependencies (ChromaDB + sentence-transformers) for enhanced vector search
in the Claudmaster AI DM module indexing system.

## Instructions

### 1. Check if RAG is already installed

Run this Python check:
```bash
python3 -c "import chromadb; import sentence_transformers; print('OK')" 2>/dev/null && echo "INSTALLED" || echo "NOT_INSTALLED"
```

If already installed, tell the user:
> RAG dependencies are already installed. ChromaDB and sentence-transformers are available.
> The Claudmaster AI DM is using vector search for module indexing.

And stop here.

### 2. Detect installation mode

Check for `pyproject.toml` in the project root to determine if this is a developer or user installation:

```bash
if [ -f "pyproject.toml" ] && grep -q 'name = "dm20-protocol"' pyproject.toml 2>/dev/null; then
    echo "MODE=developer"
else
    echo "MODE=user"
fi
```

### 3. Confirm with user

Before installing, inform the user:
> This will install ChromaDB and sentence-transformers (~2GB download).
> These enable semantic vector search for the Claudmaster AI DM module indexing.
> Without them, everything works — the system falls back to TF-IDF keyword search.
>
> Proceed?

### 4. Install based on mode

#### Developer mode
```bash
uv sync --extra rag
```

#### User mode
```bash
uv tool install "dm20-protocol[rag] @ git+https://github.com/Polloinfilzato/dm20-protocol.git" --force
```

### 5. Verify installation

After install completes, verify:
```bash
python3 -c "import chromadb; import sentence_transformers; print('OK')" 2>/dev/null && echo "SUCCESS" || echo "FAILED"
```

### 6. Report result

**On success:**
> RAG dependencies installed successfully.
> The Claudmaster AI DM will now use ChromaDB vector search for module indexing.
> No restart needed — changes take effect on the next `ask_books` or module search call.

**On failure:**
> Installation failed. The server continues to work normally using TF-IDF search.
> You can try again later with `/dm:install-rag`.
>
> If the error persists, try manually:
> - Developer mode: `cd <repo_dir> && uv sync --extra rag`
> - User mode: `uv tool install "dm20-protocol[rag] @ git+https://github.com/Polloinfilzato/dm20-protocol.git" --force`
