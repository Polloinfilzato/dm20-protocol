---
issue: 129
stream: campaign-integration
agent: python-pro
started: 2026-02-16T12:30:00Z
status: in_progress
---

# Stream 1: Campaign Integration & load_adventure MCP tool

## Scope
Implement load_adventure MCP tool, Chapter 1 entity population, module binding, and optional VectorStore RAG indexing.

## Files
- NEW: src/dm20_protocol/adventures/tools.py
- MODIFY: src/dm20_protocol/main.py (register load_adventure tool)
- NEW: tests/test_adventure_tools.py

## Progress
- Starting implementation
