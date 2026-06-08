# Modernes Base-Image: CUDA 12.4 + cuDNN 9 direkt integriert
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# Basics: FFmpeg für die Audio-Extraktion und Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Nur faster-whisper, zieht sich CTranslate2 automatisch. Kein Pytorch
RUN pip3 install --no-cache-dir faster-whisper

WORKDIR /app
COPY whisper_cli.py /app/
ENTRYPOINT ["python3", "/app/whisper_cli.py"]
