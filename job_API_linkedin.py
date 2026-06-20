"""
LinkedIn / Job Search Bot - JSearch API (Argentina)
====================================================
Usa JSearch que incluye resultados de LinkedIn, Indeed, Glassdoor, etc.
Soporta filtro por Argentina nativamente con country=ar.

Instalación:
    pip install requests rich

API Key: la misma que ya tenés en RapidAPI (JSearch).
    https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch

Uso:
    python linkedin_job_scraper.py
"""

import re
import requests
from collections import Counter
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# ──────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────
API_KEY   = "31656c98dfmsh6577b4fde8a5952p1d7640jsned03791219f6"    # Tu key de RapidAPI
QUERY     =   # Término de búsqueda (en español)
LOCATION  = "Argentina"          # País o ciudad
NUM_PAGES = 1                    # 1 página ≈ 10 resultados
# ──────────────────────────────────────────────

API_HOST   = "jsearch.p.rapidapi.com"
SEARCH_URL = f"https://{API_HOST}/search"
DETAIL_URL = f"https://{API_HOST}/job-details"

HEADERS = {
    "X-RapidAPI-Key":  API_KEY,
    "X-RapidAPI-Host": API_HOST,
}

console = Console()

# ── Tecnologías a detectar ───────────────────────────────────────────────────
TECH_KEYWORDS = {
    "python", "sql", "r", "java", "scala", "julia", "c++", "c#", "go",
    "javascript", "typescript", "bash", "matlab", "vba", "dax",
    "postgresql", "mysql", "sql server", "oracle", "mongodb", "redis",
    "bigquery", "redshift", "snowflake", "hive", "cassandra", "dynamodb",
    "sqlite", "mariadb", "teradata", "databricks",
    "power bi", "tableau", "looker", "qlik", "metabase", "superset",
    "grafana", "google data studio", "microstrategy",
    "aws", "azure", "gcp", "google cloud", "s3", "ec2", "lambda",
    "spark", "hadoop", "kafka", "airflow", "dbt", "etl", "elt",
    "luigi", "nifi", "talend", "informatica", "ssis", "pentaho", "flink",
    "machine learning", "deep learning", "scikit-learn", "tensorflow",
    "pytorch", "keras", "xgboost", "lightgbm", "nlp", "llm",
    "hugging face", "mlflow",
    "pandas", "numpy", "matplotlib", "seaborn", "plotly", "scipy",
    "statsmodels", "pyspark", "fastapi", "flask",
    "git", "github", "gitlab", "docker", "kubernetes", "linux",
    "excel", "google sheets", "jira", "confluence",
    "agile", "scrum", "kanban", "api", "rest",
}

# Empresas anónimas a ignorar
ANONYMOUS_KEYWORDS = [
    "importante empresa", "empresa confidencial", "empresa del sector",
    "empresa líder", "empresa lider", "empresa reconocida",
    "empresa de primer nivel", "confidencial",
]


def search_jobs(query: str, location: str, page: int = 1) -> list[dict]:
    params = {
        "query":    f"{query} en {location}",
        "country":  "ar",
        "language": "es",
        "page":     str(page),
        "num_pages": "1",
    }
    resp = requests.get(SEARCH_URL, headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json().get("data", []) or []


def get_job_detail(job_id: str) -> dict:
    params = {"job_id": job_id, "country": "ar", "language": "es"}
    try:
        resp = requests.get(DETAIL_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0] if isinstance(data, list) and data else (data or {})
    except Exception:
        return {}


def parse_job(raw: dict) -> dict:
    title    = raw.get("job_title") or "—"
    company  = raw.get("employer_name") or "—"
    city     = raw.get("job_city") or ""
    country  = raw.get("job_country") or ""
    loc      = f"{city}, {country}".strip(", ") or "—"
    remote   = raw.get("job_is_remote", False)
    if remote:
        loc = f"Remoto ({loc})" if loc != "—" else "Remoto"
    date     = (raw.get("job_posted_at_datetime_utc") or "—")[:10]
    url      = raw.get("job_apply_link") or raw.get("job_url") or "—"
    emp_type = raw.get("job_employment_type") or ""
    desc     = raw.get("job_description") or ""

    # Requisitos desde highlights
    highlights = raw.get("job_highlights") or {}
    requisitos = []
    for section in highlights.values():
        if isinstance(section, list):
            requisitos.extend(section)

    # Fallback: líneas de descripción
    if not requisitos and desc:
        for line in desc.split("\n"):
            line = line.strip().lstrip("•·-* ")
            if 15 < len(line) < 250:
                requisitos.append(line)

    return {
        "titulo":      title,
        "empresa":     company,
        "ubicacion":   loc,
        "fecha":       date,
        "tipo":        emp_type,
        "url":         url,
        "descripcion": desc[:600],
        "requisitos":  requisitos[:10],
    }


def extract_technologies(text: str) -> list[str]:
    text_lower = text.lower()
    found = set()
    for tech in TECH_KEYWORDS:
        pattern = r"(?<![a-z0-9])" + re.escape(tech) + r"(?![a-z0-9])"
        if re.search(pattern, text_lower):
            found.add(tech)
    return list(found)


def display_job(job: dict, index: int):
    header = Text()
    header.append(f"#{index}  ", style="bold cyan")
    header.append(job["titulo"], style="bold white")
    if job["empresa"] not in ("—", ""):
        header.append(f"  ·  {job['empresa']}", style="yellow")

    content = Text()
    meta = f"📍 {job['ubicacion']}   📅 {job['fecha']}"
    if job["tipo"]:
        meta += f"   💼 {job['tipo']}"
    content.append(meta + "\n", style="dim")

    if job["requisitos"]:
        content.append("\n📋 Requisitos:\n", style="bold green")
        for req in job["requisitos"]:
            content.append(f"  • {req}\n", style="white")
    elif job.get("descripcion"):
        content.append("\n📄 Descripción:\n", style="bold green")
        content.append(job["descripcion"][:400] + "…\n", style="white")

    content.append(f"\n🔗 {job['url']}\n", style="blue underline")
    console.print(Panel(content, title=header, border_style="bright_blue", box=box.ROUNDED))


def display_tech_ranking(jobs: list[dict]):
    counter: Counter = Counter()
    for job in jobs:
        all_text = " ".join(job["requisitos"]) + " " + job.get("descripcion", "")
        for tech in extract_technologies(all_text):
            counter[tech] += 1

    if not counter:
        console.print("\n[yellow]No se detectaron tecnologías en los requisitos.[/yellow]")
        return

    max_count = counter.most_common(1)[0][1]
    console.print("\n")
    console.print(Panel.fit(
        f"[bold white]Tecnologías más solicitadas[/bold white]\n"
        f"[dim]Basado en {len(jobs)} ofertas analizadas[/dim]",
        border_style="green"
    ))

    tech_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold green", padding=(0, 1))
    tech_table.add_column("#",           width=4,  justify="right")
    tech_table.add_column("Tecnología",  width=22)
    tech_table.add_column("Apariciones", width=10, justify="center")
    tech_table.add_column("Frecuencia",  width=35)

    for rank, (tech, count) in enumerate(counter.most_common(), start=1):
        bar_len = round((count / max_count) * 25)
        bar     = "█" * bar_len + "░" * (25 - bar_len)
        pct     = round(count / len(jobs) * 100)
        color   = "bright_green" if pct >= 50 else ("yellow" if pct >= 25 else "white")
        tech_table.add_row(
            str(rank),
            f"[bold]{tech.upper()}[/bold]",
            f"[{color}]{count}[/{color}]",
            f"[{color}]{bar}[/{color}] [dim]{pct}%[/dim]",
        )

    console.print(tech_table)


def main():
    console.print(Panel.fit(
        f"[bold cyan]LinkedIn Job Search Bot — Argentina[/bold cyan]\n"
        f"Búsqueda: [yellow]{QUERY}[/yellow]  ·  Ubicación: [yellow]{LOCATION}[/yellow]",
        border_style="cyan"
    ))

    if API_KEY == "TU_API_KEY_AQUI":
        console.print(
            "[bold red]⚠  Configurá tu API_KEY.[/bold red]\n"
            "Usá la misma key de JSearch que ya tenés en RapidAPI."
        )
        return

    all_raw = []
    with console.status("[bold green]Buscando ofertas...[/bold green]"):
        for page in range(1, NUM_PAGES + 1):
            try:
                items = search_jobs(QUERY, LOCATION, page)
                all_raw.extend(items)
            except requests.HTTPError as e:
                console.print(f"[red]Error HTTP: {e}[/red]")
                break

    if not all_raw:
        console.print("[red]No se encontraron resultados.[/red]")
        return

    # Parsear y filtrar empresas anónimas
    all_jobs = []
    for raw in all_raw:
        job = parse_job(raw)
        if any(k in job["empresa"].lower() for k in ANONYMOUS_KEYWORDS):
            continue
        all_jobs.append(job)

    console.print(f"[bold green]✔ {len(all_jobs)} ofertas encontradas[/bold green]\n")

    for i, job in enumerate(all_jobs, start=1):
        display_job(job, i)

    # Tabla resumen
    console.print("\n[bold]Resumen:[/bold]")
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("#",         width=4)
    table.add_column("Título",    width=35)
    table.add_column("Empresa",   width=25)
    table.add_column("Ubicación", width=22)
    table.add_column("Fecha",     width=12)
    for i, job in enumerate(all_jobs, start=1):
        table.add_row(str(i), job["titulo"][:34], job["empresa"][:24], job["ubicacion"][:21], job["fecha"])
    console.print(table)

    display_tech_ranking(all_jobs)


if __name__ == "__main__":
    main()