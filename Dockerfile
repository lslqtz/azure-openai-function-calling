FROM python:3.8

WORKDIR /app

ENV PIP_ROOT_USER_ACTION=ignore

COPY . .

RUN pip install -r requirements.txt

RUN pip install pyyaml

CMD ["uvicorn", "test:app", "--host", "0.0.0.0", "--port", "8000"]
