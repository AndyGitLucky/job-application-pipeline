"""
Explicit role boundaries for the pipeline's agentic responsibilities.
"""

from __future__ import annotations

AGENT_ROLES = {
    "retriever": {
        "responsibility": "Find jobs, contacts, and relevant candidate evidence",
        "modules": ["find_jobs.py", "find_contacts.py", "retrieval_context.py", "vector_store.py"],
    },
    "planner": {
        "responsibility": "Prepare score-based decisions and review routing",
        "modules": ["score_jobs.py", "decision_engine.py", "review_pipeline.py"],
    },
    "generator": {
        "responsibility": "Generate application materials and outreach text",
        "modules": ["generate_application.py"],
    },
    "executor": {
        "responsibility": "Send or submit approved applications and record outcomes",
        "modules": ["archive/auto_apply.py", "feedback_store.py"],
    },
}
