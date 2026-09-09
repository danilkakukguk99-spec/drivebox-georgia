FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home store
COPY . .
RUN mkdir -p /data && chown store:store /data
USER store
ENV DATA_DIR=/data PORT=8000
EXPOSE 8000
CMD ["gunicorn", "-c", "gunicorn.conf.py", "server.store:application"]
