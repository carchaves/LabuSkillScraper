"""
LinkedIn Job Scraper - Búsqueda directa (Playwright)
=====================================================
Scrapea linkedin.com/jobs/search igual que la barra de búsqueda nativa.
NO requiere login — usa la versión pública de LinkedIn Jobs.

Instalación:
    pip install playwright beautifulsoup4 rich lxml
    playwright install chromium

Uso:
    python linkedin_job_scraper.py
"""

import re
import time
from collections import Counter
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

# ──────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────
QUERY    = input("Puesto: ")
LOCATION = "Argentina"
HEADLESS = True       # False = ver el navegador (debug)
DELAY    = 2.0        # Segundos entre requests
MAX_JOBS = 25         # Máximo de ofertas a procesar
# ──────────────────────────────────────────────

BASE_URL = "https://www.linkedin.com/jobs/search"
console  = Console()

TECH_KEYWORDS = {
    # ── Lenguajes de programación
    "python", "sql", "r", "java", "scala", "julia", "c++", "c#", "go", "rust",
    "javascript", "html", "css", "typescript", "bash", "matlab", "vba", "dax", "php", "ruby",
    "swift", "kotlin", "perl", "fortran", "cobol", "sas", "stata", ".net",
    # ── Bases de datos
    "postgresql", "mysql", "sql server", "oracle", "mongodb", "redis",
    "bigquery", "redshift", "snowflake", "hive", "cassandra", "dynamodb",
    "sqlite", "mariadb", "teradata", "databricks", "db2", "sybase",
    # ── BI / Visualización
    "power bi", "tableau", "looker", "qlik", "metabase", "superset",
    "grafana", "google data studio", "microstrategy", "cognos",
    "spotfire", "sisense", "domo",
    # ── Cloud
    "aws", "azure", "gcp", "google cloud", "s3", "ec2", "lambda",
    "dataflow", "glue", "athena", "sagemaker",
    # ── Data Engineering / ETL
    "spark", "hadoop", "kafka", "airflow", "dbt", "etl", "elt",
    "luigi", "nifi", "talend", "informatica", "ssis", "pentaho", "flink",
    # ── ML / IA
    "machine learning", "deep learning", "scikit-learn", "tensorflow",
    "pytorch", "keras", "xgboost", "lightgbm", "nlp", "llm",
    "hugging face", "mlflow", "opencv", "spacy", "langchain",
    # ── Librerías Python
    "pandas", "numpy", "matplotlib", "seaborn", "plotly", "scipy",
    "statsmodels", "pyspark", "fastapi", "flask", "sqlalchemy", "sympy",
    # ── DevOps / Infraestructura
    "git", "github", "gitlab", "docker", "kubernetes", "linux",
    "terraform", "ansible", "jenkins", "ci/cd", "bitbucket",
    # ── Ofimática y colaboración
    "excel", "google sheets", "jira", "confluence", "notion",
    "microsoft office", "google workspace", "sharepoint", "trello", "asana",
    "slack", "teams", "zoom",
    # ── Metodologías
    "agile", "scrum", "kanban", "api", "rest", "microservices", "devops",
    "six sigma", "lean", "itil", "pmbok",
    # ── CIENTÍFICO
    "spss", "origin", "labview", "mathematica", "maple", "jupyter",
    "rstudio", "bioinformatics", "blast", "imagej", "fiji",
    "arcgis", "qgis", "solidworks", "ansys", "comsol",
    "endnote", "zotero", "latex", "mendeley",
    # ── FINANCIERO / AUDITORÍA / CONTADURÍA
    "sap", "sap fi", "sap co", "sap s/4hana", "sap erp",
    "oracle financials", "oracle erp", "netsuite", "dynamics 365",
    "quickbooks", "xero", "tango gestión", "bejerman", "odoo",
    "bloomberg", "reuters eikon", "factset", "capital iq",
    "hyperion", "anaplan", "adaptive insights", "workday",
    "caseware", "teammate", "acl analytics", "idea", "arbutus",
    "crystal reports", "cognos controller",
    "power query", "power pivot",
    # ── NEGOCIOS / CRM / MARKETING
    "salesforce", "hubspot", "zoho crm", "pipedrive", "dynamics crm",
    "marketo", "pardot", "mailchimp", "google analytics", "google ads",
    "meta ads", "facebook ads", "semrush", "ahrefs", "moz",
    "hotjar", "mixpanel", "amplitude", "segment", "braze",
    "shopify", "woocommerce", "magento", "prestashop",
    # ── DISEÑO / AUDIOVISUAL / ARTÍSTICO
    "photoshop", "illustrator", "indesign", "after effects", "premiere",
    "lightroom", "adobe xd", "figma", "sketch", "invision",
    "blender", "cinema 4d", "maya", "3ds max", "zbrush",
    "final cut pro", "davinci resolve", "avid", "pro tools",
    "ableton", "logic pro", "fl studio", "cubase",
    "unity", "unreal engine", "godot",
    "canva", "capcut", "obs",
    # ── ARQUITECTURA / CONSTRUCCIÓN / INGENIERÍA
    "autocad", "revit", "archicad", "rhino", "grasshopper",
    "sketchup", "lumion", "enscape", "v-ray",
    "civil 3d", "navisworks", "tekla", "staad pro", "etabs",
    "bim", "microstation", "allplan",
    "primavera", "ms project", "procore",
    # ── SALUD / MEDICINA
    "epic", "meditech", "hl7", "fhir", "epi info", "redcap",
    # ── LEGAL / COMPLIANCE
    "lexis nexis", "westlaw", "practical law"
}

ANONYMOUS_KEYWORDS = [
    "importante empresa", "empresa confidencial", "empresa del sector",
    "empresa líder", "empresa lider", "empresa reconocida", "confidencial",
]


def build_search_url(query: str, location: str) -> str:
    import urllib.parse
    params = urllib.parse.urlencode({
        "keywords": query,
        "location": location,
        "f_TPR":    "r2592000",  # últimos 30 días
        "sortBy":   "DD",        # más recientes primero
    })
    return f"{BASE_URL}?{params}"


def parse_job_cards(html: str) -> list[dict]:
    """Extrae las tarjetas de la página de resultados."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    # LinkedIn usa <li> con clase que contiene "jobs-search__results-list" o similar
    cards = soup.find_all("li", class_=lambda c: c and "result-card" in (c or ""))
    if not cards:
        # Selector alternativo para la versión pública
        cards = soup.find_all("div", class_=lambda c: c and "job-search-card" in (c or ""))
    if not cards:
        cards = soup.find_all("li", class_=lambda c: c and "jobs-search-results__list-item" in (c or ""))
    if not cards:
        # Fallback más genérico
        cards = soup.select("ul.jobs-search__results-list > li")

    for card in cards:
        # Título
        title_tag = card.find(["h3", "h4"], class_=lambda c: c and ("title" in (c or "") or "base-search-card__title" in (c or "")))
        if not title_tag:
            title_tag = card.find("a", class_=lambda c: c and "base-card__full-link" in (c or ""))
        title = title_tag.get_text(strip=True) if title_tag else "—"
        if not title or title == "—":
            continue

        # URL del detalle
        link_tag = card.find("a", class_=lambda c: c and "base-card__full-link" in (c or ""))
        if not link_tag:
            link_tag = card.find("a", href=lambda h: h and "/jobs/view/" in (h or ""))
        url = link_tag["href"].split("?")[0] if link_tag else "—"

        # Empresa
        company_tag = card.find(["h4", "a"], class_=lambda c: c and ("company" in (c or "") or "subtitle" in (c or "")))
        company = company_tag.get_text(strip=True) if company_tag else "—"

        # Ubicación
        loc_tag = card.find("span", class_=lambda c: c and ("location" in (c or "") or "job-search-card__location" in (c or "")))
        location = loc_tag.get_text(strip=True) if loc_tag else "—"

        # Fecha
        date_tag = card.find("time")
        date = date_tag.get("datetime", date_tag.get_text(strip=True)) if date_tag else "—"

        jobs.append({
            "titulo":      title,
            "empresa":     company,
            "ubicacion":   location,
            "fecha":       str(date)[:10],
            "url":         url,
            "requisitos":  [],
            "descripcion": "",
        })

    return jobs


def fetch_job_detail(page_pw, url: str) -> dict:
    """Navega al detalle de la oferta y extrae la descripción."""
    try:
        page_pw.goto(url, wait_until="domcontentloaded", timeout=20000)
        page_pw.wait_for_timeout(2000)
    except PlaywrightTimeout:
        pass

    soup = BeautifulSoup(page_pw.content(), "lxml")

    # Contenedor principal de descripción en LinkedIn público
    desc_tag = (
        soup.find("div", class_=lambda c: c and "description__text" in (c or "")) or
        soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in (c or "")) or
        soup.find("div", {"class": "description"}) or
        soup.find("section", class_=lambda c: c and "description" in (c or ""))
    )

    if not desc_tag:
        return {"descripcion": "—", "requisitos": []}

    full_text = desc_tag.get_text(separator="\n", strip=True)

    # Extraer items de listas
    requisitos = []
    for ul in desc_tag.find_all("ul"):
        items = [li.get_text(strip=True) for li in ul.find_all("li")
                 if len(li.get_text(strip=True)) > 10]
        requisitos.extend(items)

    # Filtrar basura
    def is_clean(line: str) -> bool:
        if re.match(r"^\d+[,\.]\d+", line):
            return False
        if len(line) > 300:
            return False
        return True

    requisitos = [r for r in requisitos if is_clean(r)]

    if not requisitos:
        lines = [l.strip() for l in full_text.split("\n") if len(l.strip()) > 20]
        requisitos = [l for l in lines if is_clean(l)][:8]

    return {
        "descripcion": full_text[:600],
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
    content.append(f"📍 {job['ubicacion']}   📅 {job['fecha']}\n", style="dim")

    if job["requisitos"]:
        content.append("\n📋 Requisitos:\n", style="bold green")
        for req in job["requisitos"]:
            content.append(f"  • {req}\n", style="white")
    elif job.get("descripcion") and job["descripcion"] != "—":
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
        console.print("\n[yellow]No se detectaron tecnologías.[/yellow]")
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
    search_url = build_search_url(QUERY, LOCATION)
    console.print(Panel.fit(
        f"[bold cyan]LinkedIn Job Scraper[/bold cyan]\n"
        f"Búsqueda: [yellow]{QUERY}[/yellow]  ·  Ubicación: [yellow]{LOCATION}[/yellow]\n"
        f"[dim]{search_url}[/dim]",
        border_style="cyan"
    ))

    all_jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page_pw = context.new_page()

        # Bloquear recursos innecesarios para acelerar
        page_pw.route("**/*.{png,jpg,jpeg,gif,svg,woff,woff2}", lambda r: r.abort())

        console.print(f"[dim]→ Cargando resultados de LinkedIn...[/dim]")
        with console.status("[bold green]Cargando página de resultados...[/bold green]"):
            try:
                page_pw.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                # Esperar que aparezcan las tarjetas de trabajo
                page_pw.wait_for_selector(
                    "ul.jobs-search__results-list, div.job-search-card, li.result-card",
                    timeout=15000
                )
                page_pw.wait_for_timeout(2000)
            except PlaywrightTimeout:
                console.print("[yellow]Timeout — guardando HTML para debug...[/yellow]")
                with open("debug_linkedin.html", "w") as f:
                    f.write(page_pw.content())

        html  = page_pw.content()
        cards = parse_job_cards(html)

        if not cards:
            console.print("[yellow]No se encontraron tarjetas — guardando HTML para debug.[/yellow]")
            with open("debug_linkedin.html", "w", encoding="utf-8") as f:
                f.write(html)
            browser.close()
            return

        console.print(f"[green]✔ {len(cards)} ofertas en la página[/green]")

        # Filtrar empresas anónimas
        cards = [c for c in cards if not any(k in c["empresa"].lower() for k in ANONYMOUS_KEYWORDS)]
        cards = cards[:MAX_JOBS]

        # Obtener detalles
        for i, job in enumerate(cards, start=1):
            console.print(f"[dim]Detalle {i}/{len(cards)}: {job['titulo']}[/dim]")
            if job["url"] and job["url"] != "—":
                detail = fetch_job_detail(page_pw, job["url"])
                job["requisitos"]  = detail["requisitos"]
                job["descripcion"] = detail["descripcion"]
            time.sleep(DELAY)
            all_jobs.append(job)

        browser.close()

    if not all_jobs:
        console.print("[red]No se obtuvieron resultados finales.[/red]")
        return

    for i, job in enumerate(all_jobs, start=1):
        display_job(job, i)

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
    copy_tech_to_clipboard(all_jobs)


def copy_tech_to_clipboard(jobs: list[dict]):
    """Genera el ranking de tecnologías en formato Notion y lo copia al portapapeles."""
    import subprocess, sys
    from datetime import date

    counter: Counter = Counter()
    for job in jobs:
        all_text = " ".join(job["requisitos"]) + " " + job.get("descripcion", "")
        for tech in extract_technologies(all_text):
            counter[tech] += 1

    if not counter:
        return

    today     = date.today().strftime("%d/%m/%Y")
    query_str = QUERY.title()
    lines = [
        f"# 🛠 Tecnologías más solicitadas — {query_str} en {LOCATION}",
        f"📅 {today}  ·  Basado en {len(jobs)} ofertas de LinkedIn",
        "",
        "| # | Tecnología | Apariciones | % de ofertas |",
        "| --- | --- | --- | --- |",
    ]

    for rank, (tech, count) in enumerate(counter.most_common(), start=1):
        pct = round(count / len(jobs) * 100)
        lines.append(f"| {rank} | {tech.upper()} | {count} | {pct}% |")

    lines += [
        "",
        f"> Búsqueda: **{QUERY}** · Ubicación: **{LOCATION}** · Fecha: {today}",
    ]

    notion_text = "\n".join(lines)

    # Copiar al portapapeles según el OS
    try:
        if sys.platform == "darwin":
            subprocess.run("pbcopy", input=notion_text.encode(), check=True)
        elif sys.platform == "win32":
            subprocess.run("clip", input=notion_text.encode("utf-16"), check=True)
        else:
            # Linux: intentar xclip, luego xsel, luego wl-copy (Wayland)
            for cmd in [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["wl-copy"]]:
                try:
                    subprocess.run(cmd, input=notion_text.encode(), check=True)
                    break
                except FileNotFoundError:
                    continue
            else:
                raise RuntimeError("No se encontró xclip, xsel ni wl-copy")

        console.print(Panel.fit(
            "[bold green]✔ Ranking copiado al portapapeles[/bold green]\n"
            "[dim]Pegalo directo en una página de Notion (soporta tabla Markdown)[/dim]",
            border_style="green"
        ))

    except Exception as e:
        console.print(Panel(
            f"[yellow]No se pudo copiar automáticamente: {e}[/yellow]\n\n"
            f"[dim]Copiá este texto manualmente:[/dim]\n\n{notion_text}",
            title="[yellow]Formato Notion[/yellow]",
            border_style="yellow"
        ))


if __name__ == "__main__":
    main()