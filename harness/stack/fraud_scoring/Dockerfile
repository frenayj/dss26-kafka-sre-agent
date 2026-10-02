FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY fraud_scorer.py inject_poison.py ./

ENV PYTHONUNBUFFERED=1
CMD ["python", "fraud_scorer.py"]
