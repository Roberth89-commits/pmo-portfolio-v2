import os
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import List
import models, schemas, database
import ai_service
from database import engine, get_db
import re

# Criar tabelas
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="PMO Portfolio Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caminho absoluto para a pasta static
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# Montar arquivos estáticos
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")

# ============ CRUD PROJETOS ============

@app.get("/api/projects", response_model=schemas.PaginatedProjects)
def list_projects(status: str = None, page: int = 1, per_page: int = 9, db: Session = Depends(get_db)):
    query = db.query(models.Project)
    if status and status != "todos":
        query = query.filter(models.Project.status == status)
    
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    
    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()
    
    return schemas.PaginatedProjects(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages
    )

@app.get("/api/projects/{project_id}", response_model=schemas.ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return project

@app.post("/api/projects", response_model=schemas.ProjectResponse)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    db_project = models.Project(**project.dict())
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@app.put("/api/projects/{project_id}", response_model=schemas.ProjectResponse)
def update_project(project_id: int, project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    for key, value in project.dict().items():
        setattr(db_project, key, value)
    db.commit()
    db.refresh(db_project)
    return db_project

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    db_project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not db_project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    db.delete(db_project)
    db.commit()
    return {"message": "Projeto removido com sucesso"}

# ============ BUSCA IA ============

@app.post("/api/ai/search", response_model=schemas.AIResponse)
def ai_search(query_data: schemas.AIQuery, db: Session = Depends(get_db)):
    query = query_data.query.lower().strip()
    projects = db.query(models.Project).all()

    answer = ""
    sources = []
    q = query

    if any(w in q for w in ["atrasado", "atrasados", "delay", "late"]):
        atrasados = [p for p in projects if p.status == "atrasado"]
        if not atrasados:
            answer = "Boa noticia! Nenhum projeto esta atrasado no momento."
        else:
            answer = "Encontrei " + str(len(atrasados)) + " projeto(s) atrasado(s):\n\n"
            for p in atrasados:
                answer += "- " + p.name + " (" + p.code + ") - Progresso: " + str(p.progress) + "%, Gerente: " + str(p.manager or "N/A") + "\n"
                answer += "  Risco: " + str(p.risks or "Nao informado") + "\n\n"
            answer += "Recomendacao: Priorizar acoes corretivas e realocar recursos."
        sources = [p.code for p in atrasados]

    elif any(w in q for w in ["orcamento", "budget", "custo", "custo total", "investimento", "dinheiro", "valor"]):
        total = 0
        for p in projects:
            val = re.sub(r"[^0-9]", "", str(p.budget or "0"))
            total += int(val) if val else 0
        answer = "O orcamento total do portfolio e de R$ " + str(round(total/1_000_000, 1)) + " milhoes (" + str(len(projects)) + " projetos).\n\n"
        answer += "Maiores investimentos:\n"
        sorted_p = sorted(projects, key=lambda x: int(re.sub(r"[^0-9]", "", str(x.budget or "0")) or 0), reverse=True)
        for p in sorted_p[:5]:
            answer += "- " + p.name + ": " + str(p.budget or "N/A") + "\n"
        sources = ["Portfolio Completo"]

    elif any(w in q for w in ["risco", "riscos", "problema", "problemas", "alerta"]):
        with_risks = [p for p in projects if p.risks and "nenhum" not in p.risks.lower()]
        answer = "Identifiquei " + str(len(with_risks)) + " projetos com riscos ativos:\n\n"
        for p in with_risks:
            answer += "- " + p.name + " (" + p.code + ") - " + str(p.risks) + "\n"
        sources = [p.code for p in with_risks]

    elif any(w in q for w in ["prioridade", "prioritario", "critico", "urgente"]):
        criticos = [p for p in projects if p.priority in ["critica", "critico", "critica", "critico"]]
        answer = "Existem " + str(len(criticos)) + " projetos de prioridade critica:\n\n"
        for p in criticos:
            answer += "- " + p.name + " (" + p.code + ") - " + str(p.progress) + "% concluido, prazo: " + str(p.deadline or "N/A") + "\n"
        if criticos:
            answer += "\nRecomendacao: Manter foco e alocacao de recursos nesses projetos."
        sources = [p.code for p in criticos]

    elif any(w in q for w in ["resumo", "status", "andamento", "visao geral", "overview", "dashboard", "portfolio"]):
        answer = "Resumo do Portfolio (" + str(len(projects)) + " projetos):\n\n"
        em_andamento = len([p for p in projects if p.status == "em-andamento"])
        concluidos = len([p for p in projects if p.status == "concluido"])
        atrasados = len([p for p in projects if p.status == "atrasado"])
        planejados = len([p for p in projects if p.status == "planejado"])
        avg_progress = sum(p.progress for p in projects) // len(projects) if projects else 0

        answer += "Concluidos: " + str(concluidos) + "\n"
        answer += "Em Andamento: " + str(em_andamento) + "\n"
        answer += "Atrasados: " + str(atrasados) + "\n"
        answer += "Planejados: " + str(planejados) + "\n\n"
        answer += "Progresso medio: " + str(avg_progress) + "%"
        sources = ["Portfolio Completo"]

    elif any(w in q for w in ["gerente", "responsavel", "lider", "quem gerencia"]):
        answer = "Gerentes de Projetos:\n\n"
        managers = {}
        for p in projects:
            m = p.manager or "Nao atribuido"
            if m not in managers:
                managers[m] = []
            managers[m].append(p)
        for m, projs in managers.items():
            answer += "- " + m + " (" + str(len(projs)) + " projeto(s)):\n"
            for p in projs:
                answer += "  * " + p.name + " [" + p.status + "]\n"
            answer += "\n"
        sources = ["Portfolio Completo"]

    elif any(w in q for w in ["prazo", "deadline", "data", "entrega", "quando termina"]):
        answer = "Prazos dos Projetos:\n\n"
        sorted_by_progress = sorted(projects, key=lambda x: x.progress)
        for p in sorted_by_progress:
            emoji = "OK" if p.status == "concluido" else "ATRASADO" if p.status == "atrasado" else "ANDAMENTO"
            answer += "[" + emoji + "] " + p.name + " - Prazo: " + str(p.deadline or "N/A") + " | Progresso: " + str(p.progress) + "%\n"
        sources = [p.code for p in sorted_by_progress]

    else:
        matched = [p for p in projects if any(term in (p.name + " " + (p.description or "")).lower() for term in q.split())]
        if matched:
            answer = "Encontrei " + str(len(matched)) + " projeto(s) relacionado(s) a sua busca:\n\n"
            for p in matched:
                answer += "- " + p.name + " (" + p.code + ")\n"
                answer += "  Status: " + p.status + " | Progresso: " + str(p.progress) + "% | Gerente: " + str(p.manager or "N/A") + "\n"
                if p.description:
                    answer += "  Desc: " + p.description[:120] + "...\n"
                answer += "\n"
            sources = [p.code for p in matched]
        else:
            answer = "Analisei sua pergunta: \"" + query + "\"\n\n"
            answer += "Tente perguntar sobre:\n"
            answer += "- Projetos atrasados\n"
            answer += "- Orcamento total\n"
            answer += "- Riscos\n"
            answer += "- Prioridades criticas\n"
            answer += "- Resumo geral do portfolio\n"
            answer += "- Prazos e deadlines\n"
            answer += "- Gerentes responsaveis"
            sources = ["Portfolio Completo"]

    return schemas.AIResponse(answer=answer, sources=sources if sources else ["Portfolio Completo"])

# ============ BUSCA IA COM GEMINI ============

@app.post("/api/ai/gemini", response_model=schemas.AIResponse)
def ai_gemini_search(query_data: schemas.AIQuery, db: Session = Depends(get_db)):
    """Busca inteligente usando Google Gemini com contexto dos projetos"""
    projects = db.query(models.Project).all()
    result = ai_service.ask_gemini(query_data.query, projects)
    return schemas.AIResponse(answer=result["answer"], sources=result["sources"])

# Seed de dados iniciais
@app.on_event("startup")
def seed_data():
    db = database.SessionLocal()
    try:
        if db.query(models.Project).count() == 0:
            seed_projects = [
                models.Project(code="PRJ-2026-001", name="Migracao Cloud AWS", 
                    description="Migracao de infraestrutura on-premise para AWS com foco em escalabilidade.",
                    status="em-andamento", priority="critica", manager="Ana Silva",
                    budget="R$ 1.200.000", progress=65, deadline="Nov/2026",
                    risks="Dependencia de terceiros para descomissionamento de servidores legados"),
                models.Project(code="PRJ-2026-002", name="App Mobile Clientes",
                    description="Desenvolvimento de aplicativo mobile para autoatendimento com integracao ao ERP.",
                    status="em-andamento", priority="alta", manager="Carlos Mendes",
                    budget="R$ 800.000", progress=45, deadline="Jan/2027",
                    risks="Prazo apertado para entrega antes da alta temporada"),
                models.Project(code="PRJ-2026-003", name="ERP Financeiro",
                    description="Implementacao de modulo financeiro avancado com BI integrado.",
                    status="atrasado", priority="alta", manager="Mariana Costa",
                    budget="R$ 950.000", progress=30, deadline="Set/2026",
                    risks="Escopo crescente (scope creep) e falta de especialistas em BI"),
                models.Project(code="PRJ-2026-004", name="Cybersecurity Upgrade",
                    description="Modernizacao da arquitetura de seguranca com SOC, SIEM e Zero Trust.",
                    status="em-andamento", priority="critica", manager="Roberto Lima",
                    budget="R$ 600.000", progress=80, deadline="Out/2026",
                    risks="Resistencia cultural a adocao de novas politicas de acesso"),
                models.Project(code="PRJ-2026-005", name="Portal RH Digital",
                    description="Portal integrado para gestao de pessoas com onboarding digital.",
                    status="concluido", priority="media", manager="Fernanda Souza",
                    budget="R$ 350.000", progress=100, deadline="Ago/2026",
                    risks="Nenhum - projeto entregue com sucesso"),
                models.Project(code="PRJ-2026-006", name="Data Lake Analytics",
                    description="Construcao de data lake para centralizacao de dados e analises preditivas.",
                    status="planejado", priority="alta", manager="Pedro Henrique",
                    budget="R$ 1.500.000", progress=5, deadline="Mar/2027",
                    risks="Qualidade inconsistente dos dados fonte de sistemas legados"),
                models.Project(code="PRJ-2026-007", name="Chatbot Atendimento",
                    description="Implementacao de chatbot com NLP para atendimento ao cliente 24/7.",
                    status="concluido", priority="media", manager="Juliana Torres",
                    budget="R$ 280.000", progress=100, deadline="Jul/2026",
                    risks="Nenhum - projeto entregue com sucesso"),
                models.Project(code="PRJ-2026-008", name="Rede SD-WAN",
                    description="Substituicao da rede MPLS por SD-WAN em todas as filiais.",
                    status="em-andamento", priority="alta", manager="Lucas Oliveira",
                    budget="R$ 720.000", progress=55, deadline="Dez/2026",
                    risks="Indisponibilidade temporaria durante migracao por filial"),
            ]
            db.add_all(seed_projects)
            db.commit()
            print("Dados iniciais inseridos!")
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
