"""
Structured candidate profile and retrieval evidence.
"""

from __future__ import annotations

PROFILE_TEXT = """
Andreas Eichmann - Applied Data Scientist, Muenchen

Erfahrung:
- 10+ Jahre industrielle Datenanalyse bei Occhio GmbH (Mess-/Testdaten, Root-Cause-Analyse, elektronische Systeme)
- Elektrotechnischer Hintergrund: PCB-Design (Altium Designer), Fehleranalyse, Systembewertung
- Fruehere Stationen: Z-Laser GmbH, Rittal GmbH (Kommunikationselektroniker)

Weiterbildung alfatraining 2023-2024 (alle Noten sehr gut):
- Deep Learning (100 Pkt.), Python (100 Pkt.), SQL (100 Pkt.)
- Machine Learning (95 Pkt.), Statistik (97 Pkt.), Data Engineering (92 Pkt.), Data Analytics (90 Pkt.)

Projekte:
- Emotion Recognition CNN: End-to-End System (TensorFlow -> ONNX -> Browser-Deployment, live unter andygitlucky.github.io)
- GPU Training Pipeline: WSL2/CUDA auf RTX 4070, vollstaendig dokumentiert

Skills: Python, TensorFlow, scikit-learn, Pandas, SQL, ETL, ONNX, Git, Altium Designer
Sprachen: Deutsch (Muttersprache), Russisch (Muttersprache), Englisch (verhandlungssicher)

Sucht: Vollzeit, Muenchen / Hybrid / Remote, bevorzugt Industrie / MedTech / IoT
Kein abgeschlossenes Hochschulstudium (Grundlagenstudium TU Muenchen + IHK-Ausbildung)
"""


PROFILE_KNOWLEDGE = [
    {
        "id": "core_industrial_data",
        "text": "10+ Jahre industrielle Datenanalyse mit Mess-, Test- und Qualitaetsdaten in produktnahen Umgebungen.",
        "category": "profile_core",
        "priority": 10,
        "tags": ["industry", "analytics", "measurement", "testing", "quality"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "core_hardware_domain",
        "text": "Elektrotechnik- und Hardware-Hintergrund mit PCB-Design, Root-Cause-Analyse und Systemverstaendnis.",
        "category": "industry_domain",
        "priority": 10,
        "tags": ["hardware", "electronics", "root_cause", "systems", "manufacturing"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "core_ml_stack",
        "text": "Praxis in Python, SQL, Machine Learning, Deep Learning und Data Engineering.",
        "category": "profile_core",
        "priority": 9,
        "tags": ["python", "sql", "ml", "deep_learning", "data_engineering"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "project_cnn_onnx",
        "text": "Eigenes KI-Projekt: CNN Emotion Recognition von Training bis ONNX Browser-Deployment.",
        "category": "project",
        "priority": 8,
        "tags": ["cnn", "computer_vision", "onnx", "deployment", "tensorflow"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "project_gpu_pipeline",
        "text": "Eigenes KI-Projekt: GPU-Training-Pipeline mit WSL2/CUDA auf RTX 4070, inklusive Experimentier-Setup.",
        "category": "project",
        "priority": 8,
        "tags": ["gpu", "cuda", "training", "pipeline", "experimentation"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "domain_preferences",
        "text": "Besonders starke Passung zu Industrie, Fertigung, IoT, MedTech und Automotive.",
        "category": "domain_preference",
        "priority": 7,
        "tags": ["industry", "manufacturing", "iot", "medtech", "automotive"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "work_mode",
        "text": "Arbeitsmodell: Muenchen, hybrid oder remote.",
        "category": "constraint",
        "priority": 5,
        "tags": ["munich", "hybrid", "remote", "location"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "education_constraint",
        "text": "Kein abgeschlossenes Hochschulstudium; Studiumspflicht ist ein relevantes Risiko fuer die Entscheidung.",
        "category": "constraint",
        "priority": 9,
        "tags": ["degree", "education", "constraint", "risk"],
        "use_cases": ["application", "market_discovery"],
    },
    {
        "id": "market_target_roles",
        "text": "Der Markt-Fallback soll auch angrenzende Rollen sichtbar machen, nicht nur reine AI/ML-Titel.",
        "category": "market_strategy",
        "priority": 3,
        "tags": ["market", "fallback", "adjacent_roles", "discovery"],
        "use_cases": ["market_discovery"],
    },
    {
        "id": "market_signal_goal",
        "text": "Ziel im Markt-Discovery-Modus: herausfinden, welche jobnahen Rollen ausserhalb AI/ML realistisch zum Profil passen.",
        "category": "market_strategy",
        "priority": 3,
        "tags": ["market", "fallback", "role_fit", "discovery"],
        "use_cases": ["market_discovery"],
    },
]


PROFILE_FACTS = [
    item["text"]
    for item in PROFILE_KNOWLEDGE
    if item["category"] != "market_strategy"
]


def knowledge_items_for(use_case: str = "application") -> list[dict]:
    return [item for item in PROFILE_KNOWLEDGE if use_case in item.get("use_cases", [])]
