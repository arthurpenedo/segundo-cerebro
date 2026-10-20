# Imagem para rodar o segundo-cerebro em servidor (laço com Ollama, MCP ou avaliação).
#   docker build -t segundo-cerebro .
#   docker run --rm -v "$PWD:/cofre" segundo-cerebro --cofre /cofre validar
#   docker run --rm -v "$PWD:/cofre" --add-host=host.docker.internal:host-gateway segundo-cerebro \
#       --cofre /cofre rodar --motor ollama --url http://host.docker.internal:11434/v1 --modelo qwen2.5:7b
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"
ENTRYPOINT ["cerebro"]
CMD ["--help"]
