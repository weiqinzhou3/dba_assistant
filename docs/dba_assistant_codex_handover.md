# DBA Assistant: Codex Handover Document

## 1. Project Context
This is a **Deep Agents SDK-based** Redis/MySQL diagnostic assistant. It follows the **Harness Engineering** philosophy: Python is a secure execution layer (Harness) and LLM is the reasoning brain.

## 2. Current Architecture
- **Orchestrator (`src/dba_assistant/orchestrator/`)**:
    - `agent.py`: Contains the unified agent builder, loads the externalized system prompt from `src/dba_assistant/prompts/unified_system_prompt.md`, uses a persistent `thread_id` for memory, and enforces the DOCX artifact contract at runtime.
    - `tools.py`: Atomic business tool definitions. All agent-facing tools now accept explicit non-sensitive parameters instead of depending on prompt-derived connection context. Remote acquisition is split into `discover_remote_rdb`, `ensure_remote_rdb_snapshot`, and `fetch_remote_rdb_via_ssh`.
- **Interface (`src/dba_assistant/interface/`)**:
    - `adapter.py`: Handles thin request normalization, secret separation, and explicit override merging. It is no longer a business-routing layer and no longer extracts Redis / SSH / MySQL endpoints from prompt prose.
    - `hitl.py`: Interactive approval and text-input collection (`collect_input`).
- **CLI (`src/dba_assistant/cli.py`)**:
    - Interactive REPL mode that preserves session state across multiple turns.

## 3. Key Accomplishments
- **Externalized System Prompt**: The unified prompt now lives in `src/dba_assistant/prompts/unified_system_prompt.md` instead of being hardcoded in Python.
- **Implemented DOCX Artifact Contract**: When the runtime request or actual tool call selects DOCX output, the final result must be a real `.docx` artifact path instead of terminal-only text.
- **Parameterized The Tool Layer**: Agent-facing tools now take explicit non-sensitive arguments such as host, port, username, path, and output path. Python no longer needs to parse these out of prompt prose before tool execution.
- **Slimmed the Application Boundary**: `application/` now stays focused on shared request models, explicit surface fields, and secret scrubbing. It no longer performs free-form business inference or connection extraction from prompt prose.
- **Removed Legacy Runtime Drift**: Production dependencies on Python implementation under `src/dba_assistant/skills/` were removed, and legacy `phase2` runtime entry points were deleted.

## 4. Current Tightening Focus
### Priority 1: Repository Hygiene
- **Task**: Remove generated artifacts such as `__pycache__`, `.pyc`, and `.DS_Store` once cleanup scope is explicitly approved.

### Priority 2: Current-State Documentation Consistency
- **Task**: Keep the main `docs/` set aligned with the tightened runtime shape: externalized prompt, repository-root `skills/`, thin `application/`, and no legacy `phase2` runtime.

### Priority 3: Capability Expansion
- **Task**: Add more repository-root skills (for example Redis inspection or CVE reporting) without reintroducing skill-directory Python business logic.

## 5. Technical Stack
- **AI**: LangChain, Deep Agents SDK
- **Parsing**: `rdb` (HdtRdbCli), `python-docx`
- **Database**: MySQL (PyMySQL)
