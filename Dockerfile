FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg is required by Whisper to read audio from the video file
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch first: the default Linux wheel bundles CUDA libraries and
# makes the image several GB larger. requirements.txt then sees torch as satisfied.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Bake the Whisper model into the image so the first /audit call does not
# download ~140 MB inside a fresh container.
RUN python -c "import whisper; whisper.load_model('base')"

# Build the FAISS index into the image (it is git-ignored, so a fresh clone
# does not have one). Fails the build if no index can be created.
RUN python backend/scripts/index_documents.py

EXPOSE 8000

CMD ["uvicorn", "backend.src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]