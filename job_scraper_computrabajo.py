"""
Job Search Bot - Computrabajo Argentina (Playwright)
=====================================================
Instalación:
    pip install playwright beautifulsoup4 rich lxml
    playwright install chromium

Uso:
    python job_scraper.py
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
QUERY     = "analista de datos"
LOCATION  = "capital-federal"          # Ej: "buenos-aires", "cordoba", o vacío = todo el país
NUM_PAGES = 1           # 1 página ≈ 20 resultados
HEADLESS  = True        # False = ver el navegador (debug)
DELAY     = 2.0         # Segundos de espera entre requests
# ──────────────────────────────────────────────

BASE_URL = "https://ar.computrabajo.com"
console  = Console()


def build_url(query: str, location: str, page: int = 1) -> str:
    q = query.strip().replace(" ", "-").lower()
    url = f"{BASE_URL}/trabajo-de-{q}"
    if location:
        url += f"-en-{location.strip().replace(' ', '-').lower()}"
    if page > 1:
        url += f"?p={page}"
    return url


def parse_listing(html: str) -> list[dict]:
    """Extrae empleos del HTML de la página de resultados."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    # Computrabajo usa <article> para cada oferta — buscamos todos
    articles = soup.find_all("article")

    # DEBUG: guarda el HTML del primer artículo para ver la estructura exacta
    if articles:
        with open("debug_article.html", "w", encoding="utf-8") as f:
            f.write(articles[0].prettify())
        console.print("[dim]→ Estructura del primer artículo guardada en debug_article.html[/dim]")

    for art in articles:
        # Título: primer <h2> o <a> con texto relevante
        h2 = art.find("h2")
        title = h2.get_text(strip=True) if h2 else "—"
        if not title or title == "—":
            continue  # saltar artículos vacíos/decorativos

        # Link al detalle
        a_tag = h2.find("a") if h2 else art.find("a", href=True)
        href  = a_tag["href"] if a_tag and a_tag.get("href") else ""
        link  = (BASE_URL + href) if href.startswith("/") else href or "—"

        # Empresa: Computrabajo la pone en un <a> con data-dt="brand",
        # o en un <p> con clase que contiene "brand"/"company"/"employer",
        # o en el segundo <p> después del h2.
        company = "—"

        # Intento 1: atributo data-dt="brand" (selector más confiable)
        brand = art.find(attrs={"data-dt": "brand"})
        if brand:
            company = brand.get_text(strip=True)

        # Intento 2: clase con "company", "brand" o "employer"
        if company == "—":
            for tag in art.find_all(["p", "span", "a"]):
                cls = " ".join(tag.get("class", []))
                if any(k in cls.lower() for k in ["company", "brand", "employer", "empresa"]):
                    company = tag.get_text(strip=True)
                    break

        # Intento 3: segundo <p> del artículo (después del título),
        # descartando textos que sean etiquetas como "Se precisa Urgente" / "Empleo destacado"
        SKIP_TEXTS = {"se precisa urgente", "empleo destacado", "destacado", "urgente", "postulado", "vista"}
        if company == "—":
            ps = art.find_all("p")
            for p in ps:
                txt = p.get_text(strip=True)
                if (txt and txt.lower() != title.lower()
                        and txt.lower() not in SKIP_TEXTS
                        and not any(s in txt.lower() for s in SKIP_TEXTS)
                        and len(txt) < 80
                        and not txt.startswith("Hace")
                        and txt.lower() not in ("ayer", "hoy")):
                    company = txt
                    break

        # Limpiar rating pegado al nombre: "3,6Ceta Capital Humano" → "Ceta Capital Humano"
        company = re.sub(r"^\d+[,\.]\d+", "", company).strip()

        # Saltar publicaciones de empresa anónima
        ANONYMOUS_KEYWORDS = [
            "importante empresa", "empresa confidencial", "empresa del sector",
            "empresa líder", "empresa lider", "empresa reconocida",
            "empresa de primer nivel", "no especificado", "confidencial",
        ]
        if not company or any(k in company.lower() for k in ANONYMOUS_KEYWORDS):
            continue

        # Ubicación: buscar patrón "Ciudad, Provincia"
        location_text = "—"
        for tag in art.find_all(["p", "span"]):
            txt = tag.get_text(strip=True)
            if "," in txt and len(txt) < 60 and txt != title:
                location_text = txt
                break

        # Fecha: buscar "Ayer", "Hace X horas", "Hoy", etc.
        fecha = "—"
        for tag in art.find_all(["p", "span", "time"]):
            txt = tag.get_text(strip=True).lower()
            if any(k in txt for k in ["ayer", "hoy", "hace", "hora", "día", "dia", "semana"]):
                fecha = tag.get_text(strip=True)
                break

        jobs.append({
            "titulo":      title,
            "empresa":     company,
            "ubicacion":   location_text,
            "fecha":       fecha,
            "url":         link,
            "requisitos":  [],
            "descripcion": "",
        })

    return jobs


def fetch_detail(page_pw, url: str) -> dict:
    """Navega al detalle de la oferta y extrae descripción + requisitos."""
    try:
        page_pw.goto(url, wait_until="domcontentloaded", timeout=20000)
        page_pw.wait_for_timeout(2000)  # esperar render JS
    except PlaywrightTimeout:
        pass

    soup = BeautifulSoup(page_pw.content(), "lxml")

    # Buscar el contenedor de descripción
    desc_tag = (
        soup.find("div", {"id": "job_description"}) or
        soup.find("div", class_=lambda c: c and "description" in (c or "").lower()) or
        soup.find("section", class_=lambda c: c and "description" in (c or "").lower()) or
        soup.find("div", class_=lambda c: c and "offer" in (c or "").lower())
    )

    if not desc_tag:
        # fallback: tomar el main o body
        desc_tag = soup.find("main") or soup.find("body")

    if not desc_tag:
        return {"descripcion": "—", "requisitos": []}

    full_text = desc_tag.get_text(separator="\n", strip=True)

    # Extraer items de listas como requisitos
    requisitos = []
    for ul in desc_tag.find_all("ul"):
        items = [li.get_text(strip=True) for li in ul.find_all("li") if len(li.get_text(strip=True)) > 5]
        requisitos.extend(items)

    # Fallback: líneas de texto como requisitos
    if not requisitos:
        lines = [l.strip() for l in full_text.split("\n") if len(l.strip()) > 20]
        requisitos = lines[:8]

    # Limpiar basura: líneas que empiezan con rating (ej: "3,6Ambiente de trabajo")
    # o que contienen concatenaciones sin sentido
    def is_clean(line: str) -> bool:
        if re.match(r"^\d+[,\.]\d+", line):          # empieza con rating
            return False
        if re.search(r"\d+[,\.]\d{1,2}[A-Z]", line): # rating pegado a texto
            return False
        if len(line) > 300:                            # párrafo demasiado largo (basura concatenada)
            return False
        return True

    requisitos = [r for r in requisitos if is_clean(r)]

    return {
        "descripcion": full_text[:600],
        "requisitos":  requisitos[:10],
    }


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


def debug_html(html: str):
    """Guarda el HTML crudo para inspección manual."""
    with open("debug_computrabajo.html", "w", encoding="utf-8") as f:
        f.write(html)
    console.print("[dim]HTML guardado en debug_computrabajo.html[/dim]")


# ── Tecnologías y herramientas conocidas ────────────────────────────────────
TECH_KEYWORDS = {
    # Lenguajes
    "python", "sql", "r", "java", "scala", "julia", "c++", "c#", "go", "rust",
    "javascript", "typescript", "bash", "matlab", "vba", "dax",
    # Bases de datos
    "postgresql", "mysql", "sql server", "oracle", "mongodb", "redis",
    "bigquery", "redshift", "snowflake", "hive", "cassandra", "dynamodb",
    "sqlite", "mariadb", "teradata", "databricks",
    # BI / Visualización
    "power bi", "tableau", "looker", "qlik", "metabase", "superset",
    "grafana", "data studio", "google data studio", "microstrategy",
    # Cloud
    "aws", "azure", "gcp", "google cloud", "s3", "ec2", "lambda",
    "cloud", "dataflow", "glue", "athena",
    # Data Engineering / ETL
    "spark", "hadoop", "kafka", "airflow", "dbt", "etl", "elt",
    "luigi", "nifi", "talend", "informatica", "ssis", "pentaho",
    "flink", "beam",
    # ML / IA
    "machine learning", "deep learning", "scikit-learn", "tensorflow",
    "pytorch", "keras", "xgboost", "lightgbm", "nlp", "llm",
    "hugging face", "mlflow", "feature engineering",
    # Librerías Python
    "pandas", "numpy", "matplotlib", "seaborn", "plotly", "scipy",
    "statsmodels", "pyspark", "fastapi", "flask", "sqlalchemy",
    # Herramientas generales
    "git", "github", "gitlab", "docker", "kubernetes", "linux",
    "excel", "google sheets", "jira", "confluence",
    # Metodologías
    "agile", "scrum", "kanban", "api", "rest", "microservices",
}


def extract_technologies(text: str) -> list[str]:
    """Detecta tecnologías mencionadas en un texto."""
    text_lower = text.lower()
    found = set()
    for tech in TECH_KEYWORDS:
        # Buscar como palabra completa (o frase)
        pattern = r"(?<![a-z0-9])" + re.escape(tech) + r"(?![a-z0-9])"
        if re.search(pattern, text_lower):
            found.add(tech)
    return list(found)


def display_tech_ranking(jobs: list[dict]):
    """Muestra el ranking de tecnologías encontradas en todos los empleos."""
    counter: Counter = Counter()

    for job in jobs:
        # Combinar requisitos + descripción para mayor cobertura
        all_text = " ".join(job["requisitos"]) + " " + job.get("descripcion", "")
        techs = extract_technologies(all_text)
        for tech in techs:
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
    tech_table.add_column("#",            width=4,  justify="right")
    tech_table.add_column("Tecnología",   width=22)
    tech_table.add_column("Apariciones",  width=10, justify="center")
    tech_table.add_column("Frecuencia",   width=35)

    for rank, (tech, count) in enumerate(counter.most_common(), start=1):
        # Barra proporcional al máximo (25 bloques = 100%)
        bar_len  = round((count / max_count) * 25)
        bar      = "█" * bar_len + "░" * (25 - bar_len)
        pct      = round(count / len(jobs) * 100)
        color    = "bright_green" if pct >= 50 else ("yellow" if pct >= 25 else "white")
        tech_table.add_row(
            str(rank),
            f"[bold]{tech.upper()}[/bold]",
            f"[{color}]{count}[/{color}]",
            f"[{color}]{bar}[/{color}] [dim]{pct}%[/dim]",
        )

    console.print(tech_table)


def main():
    console.print(Panel.fit(
        f"[bold cyan]Job Search Bot — Computrabajo Argentina[/bold cyan]\n"
        f"Búsqueda: [yellow]{QUERY}[/yellow]"
        + (f"  ·  Ubicación: [yellow]{LOCATION}[/yellow]" if LOCATION else "  ·  Todo el país"),
        border_style="cyan"
    ))

    all_jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            locale="es-AR",
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page_pw = context.new_page()

        for page_num in range(1, NUM_PAGES + 1):
            url = build_url(QUERY, LOCATION, page_num)
            console.print(f"[dim]→ {url}[/dim]")

            with console.status(f"[bold green]Cargando página {page_num}...[/bold green]"):
                try:
                    page_pw.goto(url, wait_until="networkidle", timeout=30000)
                    page_pw.wait_for_selector("article", timeout=15000)
                    page_pw.wait_for_timeout(2000)  # buffer extra para JS
                except PlaywrightTimeout:
                    console.print(f"[yellow]Timeout esperando artículos en página {page_num}.[/yellow]")

                html = page_pw.content()

            # DEBUG: guardá el HTML si no hay resultados
            jobs = parse_listing(html)
            if not jobs:
                console.print("[yellow]Sin resultados — guardando HTML para debug...[/yellow]")
                debug_html(html)
                break

            all_jobs.extend(jobs)
            console.print(f"[green]  ✔ {len(jobs)} empleos en página {page_num}[/green]")
            time.sleep(DELAY)

        if not all_jobs:
            console.print(f"\n[red]No se encontraron resultados.[/red]")
            browser.close()
            return

        console.print(f"\n[bold green]✔ {len(all_jobs)} empleos en total — obteniendo detalles...[/bold green]\n")

        for i, job in enumerate(all_jobs, start=1):
            if job["url"] and job["url"] != "—":
                console.print(f"[dim]Detalle {i}/{len(all_jobs)}: {job['titulo']}[/dim]")
                detail = fetch_detail(page_pw, job["url"])
                job["requisitos"]  = detail["requisitos"]
                job["descripcion"] = detail["descripcion"]
                time.sleep(DELAY)

        browser.close()

    for i, job in enumerate(all_jobs, start=1):
        display_job(job, i)

    # ── Resumen de empleos ──────────────────────────────────────
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

    # ── Ranking de tecnologías ──────────────────────────────────
    display_tech_ranking(all_jobs)


if __name__ == "__main__":
    main()