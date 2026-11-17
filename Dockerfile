FROM python:3.12-slim
USER root
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir openpyxl
WORKDIR /app
COPY zeroday.html server.py sheet.html template.html update.html ./
RUN mkdir -p /data && chmod -R g=u /app /data
ENV STATE_FILE=/data/state.json PORT=8080
EXPOSE 8080
USER 1001
CMD ["python", "/app/server.py"]
