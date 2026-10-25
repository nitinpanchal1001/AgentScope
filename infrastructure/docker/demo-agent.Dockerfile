FROM python:3.12-slim

RUN pip install --no-cache-dir fastapi==0.161.1 pydantic==2.14.1 uvicorn==0.54.0 \
    && groupadd --system demo && useradd --system --gid demo --home /app demo
WORKDIR /app
COPY examples/customer-support-agent/app.py /app/app.py
USER demo
EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
