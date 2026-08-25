import os
from typing import List
import google.generativeai as genai

# Configurar API Key do Gemini (do ambiente)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")
else:
    model = None

def format_projects_for_prompt(projects: List) -> str:
    """Formata os projetos em texto para o prompt da IA"""
    if not projects:
        return "Nenhum projeto cadastrado no portfolio."

    lines = []
    lines.append(f"PORTFOLIO DE PROJETOS ({len(projects)} projetos):\n")
    lines.append("=" * 60)

    for p in projects:
        status_emoji = {
            "concluido": "✅",
            "em-andamento": "🔄",
            "atrasado": "⚠️",
            "planejado": "📋"
        }.get(p.status, "📄")

        lines.append(f"\n{status_emoji} {p.name} ({p.code})")
        lines.append(f"   Status: {p.status}")
        lines.append(f"   Prioridade: {p.priority}")
        lines.append(f"   Gerente: {p.manager or 'N/A'}")
        lines.append(f"   Orçamento: {p.budget or 'N/A'}")
        lines.append(f"   Progresso: {p.progress}%")
        lines.append(f"   Prazo: {p.deadline or 'N/A'}")
        lines.append(f"   Descrição: {p.description or 'N/A'}")
        lines.append(f"   Riscos: {p.risks or 'N/A'}")
        lines.append("-" * 40)

    return "\n".join(lines)

def ask_gemini(query: str, projects: List) -> dict:
    """Envia a pergunta para o Gemini com contexto dos projetos"""

    if not model:
        return {
            "answer": "⚠️ API do Gemini não configurada.\n\nPara usar a busca com IA, configure a variável de ambiente GEMINI_API_KEY no Render.\n\nEnquanto isso, você pode usar a busca local (funciona sem API key).",
            "sources": ["Sistema"]
        }

    context = format_projects_for_prompt(projects)

    prompt = f"""Você é um assistente inteligente de um escritório de gerenciamento de projetos (PMO).
Analise os dados do portfolio abaixo e responda à pergunta do usuário de forma clara, objetiva e profissional.

Use emojis para tornar a resposta mais visual.
Se houver recomendações práticas, inclua-as.
Responda em português do Brasil.

{context}

PERGUNTA DO USUÁRIO: {query}

Responda de forma natural, como um consultor de PMO experiente."""

    try:
        response = model.generate_content(prompt)
        answer = response.text if response.text else "Não foi possível gerar uma resposta."

        # Identificar quais projetos foram mencionados na resposta
        sources = []
        for p in projects:
            if p.name.lower() in answer.lower() or p.code.lower() in answer.lower():
                sources.append(p.code)

        if not sources:
            sources = ["Portfolio Completo"]

        return {"answer": answer, "sources": sources}

    except Exception as e:
        return {
            "answer": f"❌ Erro ao consultar o Gemini: {str(e)}\n\nVerifique se a API key está válida e se há crédito disponível.",
            "sources": ["Erro"]
        }
