FROM python:3.12.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY inventory-service/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ ./shared/
COPY inventory-service/app/ ./app/
RUN useradd --uid 10001 --no-create-home appuser
USER appuser
EXPOSE 8002
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]