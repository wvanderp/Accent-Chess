FROM python:3.12-slim-bookworm
RUN sed -i 's/Components: main/Components: main contrib/' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    dosbox vice xvfb xauth xdotool libxcb1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docker/requirements.txt /app/docker/requirements.txt
RUN pip install --no-cache-dir -r /app/docker/requirements.txt
COPY src/emulation /app/src/emulation
COPY src/games /app/src/games
COPY docker/dosbox.conf /app/docker/dosbox.conf
COPY docker/smoke.py /app/docker/smoke.py
ENV PYTHONPATH=/app/src SDL_AUDIODRIVER=dummy PYTHONUNBUFFERED=1
EXPOSE 8765
CMD ["xvfb-run", "-a", "-s", "-screen 0 640x480x24 -nolisten tcp", "python3", "-m", "emulation.launch"]
