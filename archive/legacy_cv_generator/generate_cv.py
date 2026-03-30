from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
from jinja2 import Environment, FileSystemLoader, StrictUndefined

SOURCE_DIR = Path(__file__).resolve().parent.parent / "source"
if SOURCE_DIR.exists():
    sys.path.insert(0, str(SOURCE_DIR))

try:
    from env_utils import load_dotenv
except ImportError:
    load_dotenv = None


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "to", "we", "with", "you", "your",
    "our", "this", "will", "have", "has", "had", "were", "was", "their", "them", "they",
    "ability", "strong", "experience", "work", "working", "looking", "role", "team", "using",
    "knowledge", "skills", "plus", "nice", "must", "can", "across", "within", "related"
}

LATEX_REPLACEMENTS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

DEFAULT_STYLE_PROMPT = (
    "Create a modern, sharp, technically credible CV in English. "
    "Keep it concise, strong, and evidence-driven. Do not invent facts. "
    "Prefer substance over buzzwords."
)


def tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9+.#\-/ ]+", " ", text)
    tokens = []
    for token in text.split():
        token = token.strip("-./")
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def keyword_counts(job_text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    tokens = tokenize(job_text)
    for tok in tokens:
        counts[tok] = counts.get(tok, 0) + 1

    for size in (2, 3):
        for idx in range(len(tokens) - size + 1):
            phrase = " ".join(tokens[idx : idx + size])
            counts[phrase] = counts.get(phrase, 0) + 1
    return counts


def normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def score_terms(terms: Iterable[str], counts: dict[str, int]) -> float:
    score = 0.0
    for term in terms:
        norm = normalize_phrase(term)
        pieces = tokenize(norm)
        if not pieces:
            continue
        piece_score = sum(counts.get(piece, 0) for piece in pieces)
        if norm in counts:
            piece_score += counts[norm] * 2
        if len(pieces) > 1:
            piece_score += 0.5
        score += piece_score
    return score


def score_text_lines(lines: Iterable[str], counts: dict[str, int]) -> float:
    return sum(score_terms([line], counts) for line in lines)


def escape_latex(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for src, dst in LATEX_REPLACEMENTS.items():
            out = out.replace(src, dst)
        return out
    if isinstance(value, list):
        return [escape_latex(v) for v in value]
    if isinstance(value, dict):
        return {k: escape_latex(v) for k, v in value.items()}
    return value


def normalize_plain_text(value: Any) -> Any:
    if isinstance(value, str):
        replacements = {
            "\u2014": " - ",
            "\u2013": " - ",
            "\u2019": "'",
            "\u2018": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u2022": "-",
            "\u00b7": "|",
            "\u00a0": " ",
        }
        out = value
        for src, dst in replacements.items():
            out = out.replace(src, dst)
        out = unicodedata.normalize("NFKD", out).encode("ascii", "ignore").decode("ascii")
        out = re.sub(r"\s+", " ", out).strip()
        return out
    if isinstance(value, list):
        return [normalize_plain_text(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_plain_text(v) for k, v in value.items()}
    return value


@dataclass
class RankedItem:
    score: float
    payload: dict[str, Any]


def get_profile_section(profile: dict[str, Any], section: str) -> Any:
    basics = profile.get("basics", {})
    if isinstance(basics, dict) and section in basics:
        return basics.get(section)
    return profile.get(section)


def normalize_skill_entries(skills: Any) -> list[str]:
    if isinstance(skills, dict):
        result: list[str] = []
        for entries in skills.values():
            result.extend(normalize_skill_entries(entries))
        return result

    if not isinstance(skills, list):
        return []

    result: list[str] = []
    for entry in skills:
        if isinstance(entry, str):
            result.append(entry)
        elif isinstance(entry, dict) and isinstance(entry.get("name"), str):
            result.append(entry["name"])
    return result


def normalize_summary_lines(profile: dict[str, Any]) -> list[str]:
    summary_lines = profile.get("summary_candidates", profile.get("summary", []))
    if not isinstance(summary_lines, list):
        return []
    return [line for line in summary_lines if isinstance(line, str)]


def select_skills(skills: list[str], counts: dict[str, int], max_skills: int) -> list[str]:
    ranked = sorted(
        skills,
        key=lambda skill: (score_terms([skill], counts), len(skill)),
        reverse=True,
    )
    return ranked[:max_skills]


def select_experience(
    experience: list[dict[str, Any]],
    counts: dict[str, int],
    max_roles: int,
    max_bullets_per_role: int,
) -> list[dict[str, Any]]:
    ranked_roles: list[RankedItem] = []
    for item in experience:
        terms: list[str] = []
        terms.extend(item.get("tags", []))
        terms.extend(item.get("tech", []))
        terms.append(item.get("role", ""))
        terms.append(item.get("company", ""))
        bullets = item.get("bullets", [])
        score = score_terms(terms, counts) + score_text_lines(bullets, counts)
        ranked_roles.append(RankedItem(score=score, payload=item))

    ranked_roles.sort(key=lambda item: item.score, reverse=True)

    result: list[dict[str, Any]] = []
    for ranked_role in ranked_roles[:max_roles]:
        item = ranked_role.payload
        bullets = item.get("bullets", [])
        ranked_bullets = sorted(
            bullets,
            key=lambda bullet: score_terms([bullet], counts),
            reverse=True,
        )
        chosen = ranked_bullets[:max_bullets_per_role] if ranked_bullets else []
        clone = dict(item)
        clone["selected_bullets"] = chosen
        result.append(clone)
    return result


def select_projects(
    projects: list[dict[str, Any]],
    counts: dict[str, int],
    max_projects: int,
    max_bullets: int = 3,
) -> list[dict[str, Any]]:
    ranked_projects: list[RankedItem] = []
    for project in projects:
        terms: list[str] = []
        terms.extend(project.get("tech", []))
        terms.extend(project.get("tags", []))
        terms.append(project.get("name", ""))
        terms.append(project.get("subtitle", ""))
        desc_lines = project.get("description", [])
        score = score_terms(terms, counts) + score_text_lines(desc_lines, counts)
        ranked_projects.append(RankedItem(score=score, payload=project))

    ranked_projects.sort(key=lambda item: item.score, reverse=True)

    selected: list[dict[str, Any]] = []
    for ranked in ranked_projects[:max_projects]:
        project = dict(ranked.payload)
        descriptions = project.get("description", [])
        ranked_desc = sorted(
            descriptions,
            key=lambda bullet: score_terms([bullet], counts),
            reverse=True,
        )
        project["selected_description"] = ranked_desc[:max_bullets]
        selected.append(project)
    return selected


def build_summary(summary_lines: list[str], counts: dict[str, int], max_lines: int = 3) -> list[str]:
    ranked = sorted(summary_lines, key=lambda line: score_terms([line], counts), reverse=True)
    return ranked[:max_lines]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def render_template(template_dir: Path, template_name: str, context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_name)
    return template.render(**context)


def normalize_education_entries(education: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in education:
        clone = dict(item)
        label_parts = [clone.get("institution", "")]
        location = clone.get("location", "")
        if location:
            label_parts.append(location)
        clone["display_label"] = ", ".join(part for part in label_parts if part)
        normalized.append(clone)
    return normalized


def generate_context_deterministic(
    profile: dict[str, Any],
    job_text: str,
    max_projects: int,
    max_skills: int,
    max_roles: int,
    max_bullets_per_role: int,
    max_summary_lines: int,
    max_project_bullets: int,
) -> dict[str, Any]:
    counts = keyword_counts(job_text)

    links = get_profile_section(profile, "links") or {}
    context = {
        "name": get_profile_section(profile, "name") or "",
        "title": get_profile_section(profile, "title") or "",
        "location": get_profile_section(profile, "location") or "",
        "email": get_profile_section(profile, "email") or "",
        "phone": get_profile_section(profile, "phone") or "",
        "linkedin": links.get("linkedin", ""),
        "github": links.get("github", ""),
        "portfolio": links.get("portfolio", ""),
        "summary": build_summary(normalize_summary_lines(profile), counts, max_summary_lines),
        "skills": select_skills(normalize_skill_entries(profile.get("skills", [])), counts, max_skills),
        "experience": select_experience(profile.get("experience", []), counts, max_roles, max_bullets_per_role),
        "projects": select_projects(profile.get("projects", []), counts, max_projects, max_project_bullets),
        "education": normalize_education_entries(profile.get("education", [])),
        "languages": profile.get("languages", []),
    }
    return context


def build_llm_source_payload(profile: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "basics": profile.get("basics", {}),
        "summary_candidates": normalize_summary_lines(profile),
        "skills": profile.get("skills", {}),
        "experience": profile.get("experience", []),
        "projects": profile.get("projects", []),
        "education": profile.get("education", []),
        "languages": profile.get("languages", []),
        "constraints": {
            "max_summary_lines": args.max_summary_lines,
            "max_skills": args.max_skills,
            "max_roles": args.max_roles,
            "max_bullets_per_role": args.max_bullets_per_role,
            "max_projects": args.max_projects,
            "max_project_bullets": args.max_project_bullets,
            "variants": args.variants,
        },
    }


def build_llm_prompt(profile: dict[str, Any], job_text: str, style_prompt: str, args: argparse.Namespace) -> str:
    source_payload = build_llm_source_payload(profile, args)
    schema = {
        "variants": [
            {
                "variant_id": "v1",
                "label": "Clean / bold / etc",
                "title": "string",
                "summary": ["string"],
                "skills": ["string"],
                "experience": [
                    {
                        "role": "string",
                        "display_role": "string",
                        "company": "string",
                        "location": "string",
                        "start": "string",
                        "end": "string",
                        "selected_bullets": ["string"],
                    }
                ],
                "projects": [
                    {
                        "name": "string",
                        "subtitle": "string",
                        "link": "string",
                        "selected_description": ["string"],
                        "tech": ["string"],
                    }
                ],
                "education": [
                    {
                        "display_degree": "string",
                        "institution": "string",
                        "start": "string",
                        "end": "string",
                    }
                ],
                "languages": [
                    {
                        "name": "string",
                        "level": "string",
                    }
                ],
            }
        ]
    }

    return (
        "You are generating CV variants from a source-of-truth profile.\n"
        "Rules:\n"
        "- Use only facts present in the supplied profile.\n"
        "- Do not invent employers, degrees, projects, tools, metrics, responsibilities, or dates.\n"
        "- You may translate or rephrase existing facts for better English style.\n"
        "- You may omit weakly relevant items.\n"
        "- Keep the tone sharp, credible, and concise.\n"
        f"- Produce exactly {args.variants} variants.\n"
        f"- Style instruction: {style_prompt}\n"
        "- Return valid JSON only, with no markdown fences or extra commentary.\n"
        f"- JSON schema example: {json.dumps(schema, ensure_ascii=True)}\n\n"
        f"JOB TEXT:\n{job_text}\n\n"
        f"SOURCE PROFILE JSON:\n{json.dumps(source_payload, indent=2, ensure_ascii=False)}\n"
    )


def ensure_env_loaded() -> None:
    if load_dotenv is not None:
        load_dotenv(Path(__file__))


def call_openrouter(prompt: str, quality: bool = True) -> str:
    ensure_env_loaded()
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set.")

    model = os.getenv(
        "OPENROUTER_MODEL_QUALITY" if quality else "OPENROUTER_MODEL",
        "anthropic/claude-sonnet-4.6" if quality else "anthropic/claude-haiku-4.5",
    )
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    timeout = int(os.getenv("OPENROUTER_TIMEOUT", "120"))
    app_name = os.getenv("OPENROUTER_APP_NAME", "Bewerbung")
    site_url = os.getenv("OPENROUTER_SITE_URL", "")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": app_name,
    }
    if site_url:
        headers["HTTP-Referer"] = site_url

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        details: str
        try:
            details = json.dumps(response.json(), ensure_ascii=False)
        except ValueError:
            details = response.text[:500]
        raise RuntimeError(f"OpenRouter error ({response.status_code}): {details}") from exc

    response_json = response.json()
    choices = response_json.get("choices") or []
    if not choices:
        raise ValueError(f"Unexpected OpenRouter response: {response_json}")

    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "".join(text_parts).strip()

    raise ValueError(f"Could not parse OpenRouter response: {response_json}")


def extract_json_object(text: str) -> str:
    text = text.strip()
    if not text:
        raise ValueError("LLM returned an empty response.")

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    raise ValueError(f"Could not locate a JSON object in LLM response: {text[:500]}")


def normalize_llm_variant(variant: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    basics = profile.get("basics", {})
    links = basics.get("links", {})
    normalized = {
        "name": basics.get("name", ""),
        "title": variant.get("title") or basics.get("title", ""),
        "location": basics.get("location", ""),
        "email": basics.get("email", ""),
        "phone": basics.get("phone", ""),
        "linkedin": links.get("linkedin", ""),
        "github": links.get("github", ""),
        "portfolio": links.get("portfolio", ""),
        "summary": variant.get("summary", []),
        "skills": variant.get("skills", []),
        "experience": variant.get("experience", []),
        "projects": variant.get("projects", []),
        "education": variant.get("education", []),
        "languages": variant.get("languages", profile.get("languages", [])),
        "variant_id": variant.get("variant_id", ""),
        "label": variant.get("label", ""),
    }
    return normalize_plain_text(normalized)


def generate_contexts_llm(profile: dict[str, Any], job_text: str, args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    prompt = build_llm_prompt(profile, job_text, args.style_prompt, args)
    raw_text = call_openrouter(prompt, quality=not args.fast_model)
    parsed = json.loads(extract_json_object(raw_text))
    variants = parsed.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError(f"LLM response did not contain a valid variants list: {parsed}")

    contexts = [normalize_llm_variant(variant, profile) for variant in variants[: args.variants]]
    return contexts, parsed


def suffix_output_path(output_path: Path, suffix: str) -> Path:
    return output_path.with_name(f"{output_path.stem}_{suffix}{output_path.suffix}")


def compile_pdf(tex_path: Path, compiler: str) -> None:
    subprocess.run(
        [
            compiler,
            "-interaction=nonstopmode",
            "-output-directory",
            str(tex_path.parent),
            str(tex_path),
        ],
        check=True,
    )
    print(f"Wrote {tex_path.with_suffix('.pdf')}")


def write_rendered_output(
    template_dir: Path,
    template_name: str,
    context: dict[str, Any],
    output_path: Path,
    compile_pdf_enabled: bool,
    pdf_compiler: str,
) -> None:
    rendered = render_template(template_dir, template_name, escape_latex(context))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    print(f"Wrote {output_path}")
    if compile_pdf_enabled:
        compile_pdf(output_path, pdf_compiler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one or more job-specific CVs in LaTeX.")
    parser.add_argument("--profile", required=True, help="Path to profile JSON")
    parser.add_argument("--job", required=True, help="Path to job description text file")
    parser.add_argument("--output", required=True, help="Path to output .tex file")
    parser.add_argument("--template", default="template.tex.j2", help="Template filename")
    parser.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic", help="Generation mode")
    parser.add_argument("--variants", type=int, default=1, help="Number of CV variants to generate in llm mode")
    parser.add_argument("--style-prompt", default=DEFAULT_STYLE_PROMPT, help="Style instruction for llm mode")
    parser.add_argument("--prompt-file", help="Optional text file whose contents replace --style-prompt")
    parser.add_argument("--save-llm-json", action="store_true", help="Save raw LLM JSON next to the generated files")
    parser.add_argument("--fast-model", action="store_true", help="Use the cheaper OpenRouter model in llm mode")
    parser.add_argument("--compile-pdf", action="store_true", help="Compile generated .tex files to PDF")
    parser.add_argument("--pdf-compiler", default="pdflatex", help="LaTeX compiler to use when --compile-pdf is set")
    parser.add_argument("--max-projects", type=int, default=2, help="Maximum number of projects")
    parser.add_argument("--max-skills", type=int, default=12, help="Maximum number of skills")
    parser.add_argument("--max-roles", type=int, default=3, help="Maximum number of experience entries")
    parser.add_argument("--max-bullets-per-role", type=int, default=3, help="Maximum bullets per role")
    parser.add_argument("--max-summary-lines", type=int, default=3, help="Maximum summary lines")
    parser.add_argument("--max-project-bullets", type=int, default=3, help="Maximum bullets per project")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile_path = Path(args.profile)
    job_path = Path(args.job)
    output_path = Path(args.output)

    if args.prompt_file:
        args.style_prompt = load_text(Path(args.prompt_file)).strip()

    profile = load_json(profile_path)
    job_text = load_text(job_path)
    template_dir = Path(__file__).resolve().parent

    if args.mode == "deterministic":
        context = generate_context_deterministic(
            profile=profile,
            job_text=job_text,
            max_projects=args.max_projects,
            max_skills=args.max_skills,
            max_roles=args.max_roles,
            max_bullets_per_role=args.max_bullets_per_role,
            max_summary_lines=args.max_summary_lines,
            max_project_bullets=args.max_project_bullets,
        )
        write_rendered_output(
            template_dir,
            args.template,
            context,
            output_path,
            args.compile_pdf,
            args.pdf_compiler,
        )
        return

    contexts, raw_llm = generate_contexts_llm(profile, job_text, args)

    if args.save_llm_json:
        llm_json_path = suffix_output_path(output_path, "llm")
        llm_json_path = llm_json_path.with_suffix(".json")
        llm_json_path.write_text(json.dumps(raw_llm, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {llm_json_path}")

    for idx, context in enumerate(contexts, start=1):
        variant_suffix = f"v{idx}" if len(contexts) > 1 else "v1"
        variant_output = suffix_output_path(output_path, variant_suffix)
        write_rendered_output(
            template_dir,
            args.template,
            context,
            variant_output,
            args.compile_pdf,
            args.pdf_compiler,
        )


if __name__ == "__main__":
    main()
