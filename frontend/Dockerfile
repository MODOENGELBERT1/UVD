FROM python:3.11-slim
WORKDIR /app
COPY . .
ENV PORT=8080
CMD python -m http.server ${PORT} --directory .
