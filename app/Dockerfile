FROM python:3.10-slim

# uv (Astral): instalador/resolvedor de pacotes Python, 10-100x mais rápido
# que pip — copiado direto da imagem oficial, sem precisar instalar via pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

EXPOSE 8501

CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
