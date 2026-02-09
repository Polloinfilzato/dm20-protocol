# Parallel Tasks Overview

Quick reference for task parallelization in the Claudmaster epic.

## Dependency Graph

```
                                    ┌──────────────────┐
                                    │  #33 Directory   │
                                    │    Structure     │
                                    │   (FOUNDATION)   │
                                    └────────┬─────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────────┐
              │                              │                              │
              ▼                              ▼                              ▼
    ┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
    │ #34 Orchestrator│            │ #35 Basic       │            │ #37 ChromaDB    │
    │                 │            │     Narrator    │            │   Vector Store  │
    └────────┬────────┘            └────────┬────────┘            └────────┬────────┘
             │                              │                              │
             │                              │                              ▼
             │                              │                    ┌─────────────────┐
             │                              │                    │ #38 Adventure   │
             │                              │                    │  Module Parser  │
             │                              │                    └────────┬────────┘
             │                              │                              │
             │                              │                              ▼
             │                              │                    ┌─────────────────┐
             │                              │                    │ #39 Module      │
             │                              │                    │    Chunking     │
             │                              │                    └────────┬────────┘
             │                              │                              │
             └──────────────────────────────┼──────────────────────────────┘
                                            │
                                            ▼
                              ┌──────────────────────────┐
                              │  PHASE 3+ TASKS          │
                              │  (after foundation)      │
                              └──────────────────────────┘
```

## Execution Waves

Tasks grouped by when they can be started. Within each wave, all tasks can run in parallel.

### Wave 1: Foundation (Start immediately)
| Task | Name | Est. Hours |
|------|------|------------|
| **#33** | Directory Structure and Base Classes | 6h |

### Wave 2: Core Components (After #33)
| Task | Name | Est. Hours | Can Parallel With |
|------|------|------------|-------------------|
| **#34** | Orchestrator Skeleton | 10h | #35, #37 |
| **#35** | Basic Narrator Agent | 8h | #34, #37 |
| **#37** | ChromaDB Vector Store Setup | 6h | #34, #35 |

### Wave 3: Module Integration (After Wave 2)
| Task | Name | Depends On | Can Parallel With |
|------|------|------------|-------------------|
| **#36** | Claudmaster Configuration MCP Tool | #34 | #38 |
| **#38** | Adventure Module Parser | #37 | #36 |

### Wave 4: Module Pipeline (After #38)
| Task | Name | Depends On | Can Parallel With |
|------|------|------------|-------------------|
| **#39** | Module Content Chunking | #38 | - |
| **#40** | Module Keeper Agent | #39 | - |
| **#41** | Campaign Module Binding | #40 | - |

### Wave 5: Full Narrative (After #34, #35)
| Task | Name | Can Parallel With |
|------|------|-------------------|
| **#42** | Enhanced Narrator with NPC Dialogue | #43, #45, #46 |
| **#43** | Archivist Agent | #42, #44, #45, #46 |
| **#44** | Player Action Interpretation | #45, #46 |
| **#45** | Combat Narration System | #42, #43, #44, #46 |
| **#46** | Scene Atmosphere and Pacing | #42, #43, #44, #45 |

### Wave 6: Consistency (After Wave 5)
| Task | Name | Can Parallel With |
|------|------|-------------------|
| **#47** | Fact Tracker System | #50 |
| **#48** | NPC Knowledge State Tracking | - |
| **#49** | Contradiction Detection | - |
| **#50** | Timeline and Location State | #47 |

### Wave 7: Improvisation (After #40, #47)
| Task | Name | Can Parallel With |
|------|------|-------------------|
| **#51** | Improvisation Level System | #54 |
| **#52** | Locked/Flexible Elements Config | - |
| **#53** | Module Fidelity Enforcement | - |
| **#54** | Canonical vs Improvised Tagging | #51 |

### Wave 8: Companions (After #42, #43)
| Task | Name | Can Parallel With |
|------|------|-------------------|
| **#55** | Companion NPC Profiles | #57 |
| **#56** | AI Combat Tactics for Companions | - |
| **#57** | Companion Roleplay and Dialogue | #55 |
| **#58** | Player Guidance System | - |

### Wave 9: Multi-Player (After #43, #44)
| Task | Name | Can Parallel With |
|------|------|-------------------|
| **#59** | Multiple PC Tracking | #62 |
| **#60** | Turn Distribution and Management | - |
| **#61** | Split Party Handling | - |
| **#62** | Player-Specific Information | #59 |

### Wave 10: MCP Tools & Polish (After all agents)
| Task | Name | Can Parallel With |
|------|------|-------------------|
| **#63** | start_claudmaster_session Tool | #64, #65, #67 |
| **#64** | player_action Tool | #63, #65, #67 |
| **#65** | end_session/get_session_state Tools | #63, #64, #67 |
| **#66** | Session Continuity and Recaps | - |
| **#67** | Error Handling and Recovery | #63, #64, #65 |
| **#68** | Performance Optimization | - |

## Critical Path

The longest dependency chain that determines minimum project duration:

```
#33 → #37 → #38 → #39 → #40 → #41 → #51 → #52 → #53 → #66 → #68
 6h    6h    10h    8h    10h   6h    6h    6h    8h    8h    8h

Total Critical Path: ~82 hours
```

## Quick Start Recommendations

### Solo Developer
Start with Wave 1, then pick ONE track:
- **Narrative Track**: #33 → #34 → #35 → #42 → #43
- **Module Track**: #33 → #37 → #38 → #39 → #40

### Two Developers
- Dev A: Narrative Track (#34, #35, #42, #43)
- Dev B: Module Track (#37, #38, #39, #40)

### Maximum Parallelism (3+ developers)
Wave 2 allows 3 tasks simultaneously: #34, #35, #37

## Legend

- **Bold #XX** = GitHub Issue number
- **Est. Hours** = Estimated effort
- **Depends On** = Must complete before starting
- **Can Parallel With** = Safe to work on simultaneously
