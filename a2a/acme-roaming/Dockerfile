FROM python:3.12-slim
RUN pip install --no-cache-dir "a2a-sdk[http-server]==1.2.2" "uvicorn==0.54.0"
COPY agent.py /app/agent.py
CMD ["python", "-u", "/app/agent.py"]
