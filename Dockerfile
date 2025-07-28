FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PY=3.12
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        software-properties-common \
        curl ca-certificates gnupg \
        git nano vim lsof

RUN add-apt-repository -y ppa:deadsnakes/ppa && apt-get update && \
    apt-get install -y --no-install-recommends \
        python${PY} python${PY}-dev python${PY}-venv && \
    python${PY} -m ensurepip && \
    python${PY} -m pip install -U pip setuptools wheel && \
    ln -sf /usr/bin/python${PY} /usr/local/bin/python

RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app
COPY . .

RUN python${PY} -m venv /app/.venv --prompt ""

RUN echo 'export VIRTUAL_ENV_DISABLE_PROMPT=1' >> /root/.bashrc && \
    echo 'source /app/.venv/bin/activate' >> /root/.bashrc

RUN /app/.venv/bin/pip install Jupyter jupyterlab

CMD ["/bin/bash"]
