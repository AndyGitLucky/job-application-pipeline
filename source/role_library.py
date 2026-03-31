from __future__ import annotations

import re

from source.embeddings_client import embed_texts, embeddings_enabled
from source.vector_store import cosine_similarity

ROLE_LIBRARY = [
    {
        "name": "ML Engineer",
        "text": "Build and deploy machine learning systems with Python, deep learning, model evaluation, data pipelines, and production-oriented iteration.",
        "tags": ["ml", "deep learning", "python", "deployment", "model evaluation"],
    },
    {
        "name": "Machine Learning Engineer",
        "text": "Applied machine learning engineering focused on training, evaluation, production integration, and robust model pipelines.",
        "tags": ["machine learning", "mlops", "python", "production", "pipelines"],
    },
    {
        "name": "Applied AI Engineer",
        "text": "Translate AI methods into working products, build applied ML systems, and connect models with real-world operational needs.",
        "tags": ["applied ai", "product", "engineering", "deployment"],
    },
    {
        "name": "AI Engineer",
        "text": "Generalist AI engineering across data, models, experimentation, and deployment with strong Python and systems thinking.",
        "tags": ["ai", "python", "deployment", "experimentation"],
    },
    {
        "name": "Data Scientist",
        "text": "Model data-driven decisions with statistics, machine learning, experimentation, and communication of analytical findings.",
        "tags": ["statistics", "machine learning", "analytics", "experimentation"],
    },
    {
        "name": "Applied Data Scientist",
        "text": "Industry-facing data scientist role focused on practical machine learning, analytics, experimentation, and product impact.",
        "tags": ["applied", "data science", "ml", "industry"],
    },
    {
        "name": "Data Engineer",
        "text": "Design data pipelines, ETL workflows, SQL transformations, and scalable data preparation for analytics and machine learning.",
        "tags": ["data engineering", "etl", "sql", "pipelines"],
    },
    {
        "name": "Analytics Engineer",
        "text": "Bridge analytics and engineering with SQL, metrics, transformation layers, quality checks, and decision support.",
        "tags": ["analytics", "sql", "metrics", "quality"],
    },
    {
        "name": "Decision Scientist",
        "text": "Use statistics, experimentation, measurement, and business reasoning to improve decisions and quantify impact.",
        "tags": ["statistics", "measurement", "decision making", "experimentation"],
    },
    {
        "name": "Optimization Engineer",
        "text": "Improve technical systems through optimization, modeling, efficiency analysis, constraints, and measurable performance gains.",
        "tags": ["optimization", "systems", "efficiency", "analysis"],
    },
    {
        "name": "MLOps Engineer",
        "text": "Operationalize machine learning with pipelines, reproducibility, deployment, monitoring, and infrastructure integration.",
        "tags": ["mlops", "deployment", "pipelines", "monitoring"],
    },
    {
        "name": "ML Systems Engineer",
        "text": "Engineer performant ML systems with inference, deployment, acceleration, GPU-aware workflows, and production constraints.",
        "tags": ["inference", "deployment", "gpu", "systems"],
    },
    {
        "name": "Inference Engineer",
        "text": "Focus on efficient inference, model serving, acceleration, optimization, and runtime performance in production.",
        "tags": ["inference", "runtime", "optimization", "deployment"],
    },
    {
        "name": "AI Platform Engineer",
        "text": "Build internal platforms for model training, evaluation, experiment tracking, data access, and scalable AI workflows.",
        "tags": ["platform", "ml", "experimentation", "infrastructure"],
    },
    {
        "name": "Computer Vision Engineer",
        "text": "Develop vision models with OpenCV, CNNs, image processing, deep learning, and real-time inference for technical products.",
        "tags": ["computer vision", "opencv", "cnn", "real-time inference"],
    },
    {
        "name": "Robotics AI Engineer",
        "text": "Apply machine learning and perception to robotics, autonomy, sensor interpretation, and real-world technical systems.",
        "tags": ["robotics", "perception", "autonomy", "sensors"],
    },
    {
        "name": "Industrial AI Engineer",
        "text": "Apply AI and data methods to industrial systems, measurement data, technical diagnostics, and operational optimization.",
        "tags": ["industrial ai", "measurement", "technical systems", "diagnostics"],
    },
    {
        "name": "AI Solutions Engineer",
        "text": "Connect AI capabilities with customer or product needs, turning ML methods into robust technical solutions.",
        "tags": ["solutions", "applied ai", "technical communication", "deployment"],
    },
    {
        "name": "Technical AI Analyst",
        "text": "Analyze technical data, detect patterns and anomalies, and translate findings into structured engineering decisions.",
        "tags": ["analysis", "technical systems", "anomaly detection", "quality"],
    },
    {
        "name": "Perception Engineer",
        "text": "Build perception components with computer vision, sensor data, machine learning, and evaluation under real-world constraints.",
        "tags": ["perception", "computer vision", "sensors", "evaluation"],
    },
]

STOPWORDS = {
    "and",
    "oder",
    "der",
    "die",
    "das",
    "mit",
    "fuer",
    "und",
    "ein",
    "eine",
    "the",
    "role",
    "job",
    "machine",
    "learning",
    "engineer",
    "scientist",
    "data",
    "ai",
}


def build_profile_semantic_text(profile: dict) -> str:
    basics = profile.get("basics") or {}
    summary = " ".join(str(item).strip() for item in profile.get("summary_candidates", []) if str(item).strip())
    skills = []
    for values in (profile.get("skills") or {}).values():
        if isinstance(values, list):
            skills.extend(str(item).strip() for item in values if str(item).strip())
    project_bits = []
    for item in profile.get("projects", []) or []:
        project_bits.append(str(item.get("name") or "").strip())
        project_bits.extend(str(tag).strip() for tag in item.get("tags", []) if str(tag).strip())
        project_bits.extend(str(tag).strip() for tag in item.get("tech", []) if str(tag).strip())
    experience_bits = []
    for item in profile.get("experience", []) or []:
        experience_bits.append(str(item.get("role") or "").strip())
        experience_bits.extend(str(tag).strip() for tag in item.get("tags", []) if str(tag).strip())
        experience_bits.extend(str(tag).strip() for tag in item.get("tech", []) if str(tag).strip())
    topics = [str(item).strip() for item in profile.get("certifications_or_topics", []) if str(item).strip()]
    parts = [
        f"title: {basics.get('title', '')}",
        f"summary: {summary}",
        f"skills: {', '.join(skills)}",
        f"experience: {', '.join(experience_bits)}",
        f"projects: {', '.join(project_bits)}",
        f"topics: {', '.join(topics)}",
    ]
    return "\n".join(part for part in parts if part.strip())


def rank_roles_for_profile(profile: dict, *, top_k: int = 8) -> list[dict]:
    profile_text = build_profile_semantic_text(profile)
    provider = "lexical_fallback"
    semantic_scores: dict[str, float] = {}

    if embeddings_enabled():
        try:
            texts = [profile_text, *[role["text"] for role in ROLE_LIBRARY]]
            vectors = embed_texts(texts)
            profile_vector = vectors[0]
            for role, vector in zip(ROLE_LIBRARY, vectors[1:]):
                semantic_scores[role["name"]] = cosine_similarity(profile_vector, vector)
            provider = "embedding_api"
        except Exception:
            provider = "lexical_fallback"

    profile_tokens = _tokenize(profile_text)
    ranked = []
    for role in ROLE_LIBRARY:
        role_text = f"{role['name']} {role['text']} {' '.join(role.get('tags', []))}"
        role_tokens = _tokenize(role_text)
        lexical = _jaccard_similarity(profile_tokens, role_tokens)
        semantic = semantic_scores.get(role["name"], 0.0)
        score = semantic + lexical
        ranked.append(
            {
                "term": role["name"],
                "score": round(score, 4),
                "semantic_score": round(float(semantic), 4),
                "lexical_score": round(float(lexical), 4),
                "strategy": "semantic",
                "provider": provider,
            }
        )

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:top_k]


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z0-9_+-]{3,}", (text or "").lower())
    return {word for word in words if word not in STOPWORDS}


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)
