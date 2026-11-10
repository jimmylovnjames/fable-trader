FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fabletrader fabletrader
COPY config.yaml .
# mount /app/state and set state_file: state/state.json to persist across restarts
ENTRYPOINT ["python", "-m", "fabletrader"]
CMD ["run"]
