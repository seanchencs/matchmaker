FROM python:3.10-slim

WORKDIR /app

COPY ./ .

ENV PYTHONPATH=${PYTHONPATH}:${PWD}

RUN pip3 install poetry==1.2.2
RUN poetry config virtualenvs.create false
RUN poetry install

# install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

CMD ["poetry", "run", "python3", "main.py"]