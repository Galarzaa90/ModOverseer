FROM python:3.12-alpine

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY overseer.py .
COPY reddit.py .

CMD ["python", "overseer.py"]
