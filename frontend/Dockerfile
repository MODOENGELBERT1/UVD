FROM python:3.11-slim
WORKDIR /app
COPY . .
ENV PORT=8080
# ${PORT:-8080} : évite un crash si PORT n'est pas fourni
CMD ["sh", "-c", "python -m http.server ${PORT:-8080} --directory ."]
