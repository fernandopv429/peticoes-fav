# Mesmo padrão da cct-api, que já roda no Coolify.
# Chromium NÃO é instalado aqui de propósito: o PDF é gerado pelo Gotenberg,
# chamado via webhook do n8n (que detém a credencial Basic auth). Isso mantém a
# imagem em ~200 MB em vez de ~800 MB.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements antes do código: muda pouco, então o Coolify reaproveita esta
# camada e o rebuild de uma correção de texto não reinstala tudo.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates

# O template e os assets do timbrado precisam estar na imagem: o pipeline lê
# templates/modelo.html e templates/assets/*.png em disco. Falhar aqui, no
# build, é melhor do que descobrir no primeiro caso real.
RUN test -f templates/modelo.html \
 && test -f templates/assets/logo_primeira.png \
 && test -f templates/assets/marca_demais.png \
 && test -f templates/assets/rodape_primeira.png

# Não roda como root. A aplicação não escreve em disco — só lê template e fala
# HTTP —, então um usuário sem privilégio basta.
RUN useradd --create-home --uid 10001 fav
USER fav

EXPOSE 8100

# O Coolify usa isto para decidir se o deploy subiu. /health não exige API_KEY.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/health',timeout=4).status==200 else 1)"

# Um worker só: a geração é longa (IA + 3 renders) e o gargalo é I/O externo,
# não CPU. Mais workers multiplicariam o uso de memória sem ganho.
CMD ["uvicorn", "app.servico:app", "--host", "0.0.0.0", "--port", "8100", \
     "--timeout-keep-alive", "300", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
