"""
Seed Postgres with synthetic JiraIssue + JiraEmbedding rows that will show up as
"similar" to a target issue when using mock embeddings.

Why:
- Mock embeddings are NOT semantic; similarity will look random.
- For demos/tests, we can create embeddings intentionally close to the target's embedding
  so similarity search returns predictable results.

Usage (from repo root):
  python scripts/db/seed_mock_similar_jira.py --target-issue-key SYSCROS-131125 --count 5

Optional:
  --prefix MOCKSIM
  --similarity 0.95   (cosine target, 0..0.999)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List


def _setup_imports() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root / "backend"))


def _l2_normalize(v: List[float]) -> List[float]:
    import math

    n = math.sqrt(sum((x * x) for x in v)) or 1.0
    return [float(x / n) for x in v]


def _make_near_vector(*, base: List[float], target_cosine: float, seed: int) -> List[float]:
    """
    Construct a vector with approximately the requested cosine similarity to `base`.
    Assumes base is already L2-normalized (we enforce it).
    """
    import math
    import random

    base = _l2_normalize(base)
    d = len(base)
    if d == 0:
        raise ValueError("Base embedding is empty.")

    # Clamp to safe range
    c = float(target_cosine)
    if c >= 1.0:
        c = 0.999
    if c <= -1.0:
        c = -0.999

    rng = random.Random(int(seed) & 0xFFFFFFFF)

    # Create a random direction roughly orthogonal to base
    noise = [rng.uniform(-1.0, 1.0) for _ in range(d)]
    dot = sum((noise[i] * base[i]) for i in range(d))
    # subtract projection
    ortho = [noise[i] - dot * base[i] for i in range(d)]
    ortho = _l2_normalize(ortho)

    # new = c*base + sqrt(1-c^2)*ortho
    s = math.sqrt(max(0.0, 1.0 - (c * c)))
    v = [c * base[i] + s * ortho[i] for i in range(d)]
    return _l2_normalize(v)


def main() -> int:
    _setup_imports()

    parser = argparse.ArgumentParser()
    parser.add_argument("--target-issue-key", required=True)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--prefix", default="MOCKSIM")
    parser.add_argument("--similarity", type=float, default=0.95)
    args = parser.parse_args()

    from app.db.session import SessionLocal
    from app.models.jira import JiraEmbedding, JiraIssue
    from app.services.embeddings import generate_embedding
    from app.agents.tools.jira_tools import get_issue_from_db

    target_key = str(args.target_issue_key).strip()
    if not target_key:
        raise SystemExit("Empty --target-issue-key")

    # Ensure we are in mock mode for deterministic behavior
    os.environ.setdefault("USE_MOCK_EMBEDDING", "true")

    # Fetch target issue from DB and build query text
    issue = get_issue_from_db(ctx={"inputs": {}, "steps": {}}, issue_key=target_key)
    base_text = (issue or {}).get("embedding_text") or ""
    if not base_text.strip():
        raise SystemExit(f"Target issue {target_key} has no embedding_text; ensure it exists in DB.")

    base_emb = generate_embedding(base_text, task_type="retrieval_query")
    if not isinstance(base_emb, list) or len(base_emb) == 0:
        raise SystemExit("Failed to generate base embedding.")
    base_emb = [float(x) for x in base_emb]

    db = SessionLocal()
    created = 0
    try:
        for i in range(1, int(args.count) + 1):
            k = f"{args.prefix}-{i}"
            # Create an embedding near the target embedding
            emb = _make_near_vector(base=base_emb, target_cosine=float(args.similarity), seed=hash(k))

            # Create a synthetic issue
            syn = JiraIssue(
                issue_key=k,
                jira_id=None,
                summary=f"[MOCK] Similar to {target_key}: synthetic case #{i}",
                description=f"This is synthetic data seeded for demo. Intended to be near {target_key}.",
                status="Closed",
                priority="P3",
                assignee="mock-user",
                issue_type="Bug",
                program_theme="MOCK",
                labels=["mock", "seed"],
                components=((issue.get("components") or []) if isinstance(issue.get("components"), list) else ["Mock"]),
                comments=[{"body": f"Synthetic comment: seeded near {target_key} (i={i})."}],
                url=None,
                raw={"seeded": True, "target": target_key, "i": i},
            )

            db.merge(syn)
            db.merge(JiraEmbedding(issue_key=k, embedding=emb))
            created += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # Keep output ASCII-friendly for Windows consoles
    print(f"Seeded {created} synthetic issues near {target_key} (prefix={args.prefix}, cosine~{args.similarity}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

