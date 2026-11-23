# ESPHome CLI with everything needed to build ESP32 firmware and the SDL simulator
# (ESPHome `host` platform). The ESPHome version comes from requirements.txt;
# build with `--build-arg ESPHOME_LATEST=true` to test the newest release instead.
FROM python:3.12-slim-trixie

ARG ESPHOME_LATEST=false

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      pkg-config \
      libsdl2-dev \
      git \
      ca-certificates \
      curl \
      openssh-client \
      libusb-1.0-0 \
      xvfb \
      xauth \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN if [ "$ESPHOME_LATEST" = "true" ]; then \
      pip install --no-cache-dir --upgrade esphome; \
    else \
      pip install --no-cache-dir -r /tmp/requirements.txt; \
    fi

# The repo is bind-mounted from another OS user; let git (remote packages) work on it.
RUN git config --system --add safe.directory '*'

# Build output and toolchains (ESP-IDF, PlatformIO) live in a named volume mounted at
# /cache (see compose.yaml), not in the bind-mounted repo: much faster on Windows/macOS,
# survives container restarts and keeps the working tree clean.
ENV ESPHOME_DATA_DIR=/cache/esphome \
    PLATFORMIO_CORE_DIR=/cache/platformio \
    XDG_CACHE_HOME=/cache/xdg \
    ESPHOME_PREFDIR=/cache/prefs \
    PYTHONUNBUFFERED=1

WORKDIR /config
ENTRYPOINT ["esphome"]
CMD ["--help"]
