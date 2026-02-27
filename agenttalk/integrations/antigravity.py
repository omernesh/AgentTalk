"""
AgentTalk Antigravity integration helper.

Provides register_antigravity_hooks() which copies the AgentTalk skill and
workflow files to the Antigravity global directories.

Called by: agenttalk setup --antigravity
"""
import shutil
from pathlib import Path


# ---------------------------------------------------------------------------
# Antigravity directory discovery
# ---------------------------------------------------------------------------

def _antigravity_skills_dir() -> Path:
    """
    Return the Antigravity skills directory.

    Antigravity uses ~/.gemini/antigravity/skills/ on all platforms
    (home-relative, no OS-specific branching needed).
    """
    return Path.home() / ".gemini" / "antigravity" / "skills"


def _antigravity_workflows_dir() -> Path:
    """
    Return the Antigravity global workflows directory.

    Always Path.home() / ".gemini" / "antigravity" / "global_workflows".
    """
    return Path.home() / ".gemini" / "antigravity" / "global_workflows"


def _integration_files_dir() -> Path:
    """
    Return the integrations/antigravity/ directory relative to this file.

    Resolves to the repo root's integrations/antigravity/ when running from
    source: Path(__file__).parent.parent.parent / "integrations" / "antigravity"
    """
    candidate = Path(__file__).parent.parent.parent / "integrations" / "antigravity"
    if not candidate.exists():
        raise FileNotFoundError(
            f"Antigravity integration files directory not found: {candidate}\n"
            "Ensure you are running from the AgentTalk source tree or that the "
            "integration files were included in the installed package."
        )
    return candidate


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_antigravity_hooks() -> None:
    """
    Copy AgentTalk skill and workflow files to Antigravity global directories.

    Creates directories if they do not exist.
    Idempotent: re-running overwrites with current versions.

    Validates that both source files exist before creating any destination
    directories or performing any copy, so the installation is never left in
    a partial state.
    """
    src_dir = _integration_files_dir()

    skill_src = src_dir / "SKILL.md"
    workflow_src = src_dir / "session_workflow.md"

    missing = [p for p in (skill_src, workflow_src) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Antigravity integration source files not found:\n"
            + "\n".join(f"  {p}" for p in missing)
        )

    skills_dir = _antigravity_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)

    workflows_dir = _antigravity_workflows_dir()
    workflows_dir.mkdir(parents=True, exist_ok=True)

    # Copy skill file
    shutil.copy2(skill_src, skills_dir / "agenttalk.md")

    # Copy session workflow
    shutil.copy2(workflow_src, workflows_dir / "agenttalk_start.md")

    print(f"  Antigravity skill installed: {skills_dir / 'agenttalk.md'}")
    print(f"  Antigravity workflow installed: {workflows_dir / 'agenttalk_start.md'}")
    print("\n  To activate: open Antigravity, the agenttalk skill is now available.")
    print("  Optionally install the VS Code extension VSIX for a UI status bar:")
    print("    integrations/vscode/agenttalk-vscode-1.0.0.vsix (Extensions: Install from VSIX)")
