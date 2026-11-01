# ============================================================================
# Multi-stage Docker build for AKKI AI Backend
# ============================================================================

# Stage 1: Build — install Python deps into an isolated prefix
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime — lean production image
FROM python:3.12-slim

WORKDIR /app

# Runtime libs plus the real security binaries the exploit tools shell out to
# (nmap, nikto, hydra, hashcat, john, sqlmap) and gobuster (pinned release).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    nmap \
    hydra \
    hashcat \
    john \
    sqlmap \
    perl \
    libnet-ssleay-perl \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && case "$(dpkg --print-architecture)" in arm64) GOBARCH=arm64 ;; *) GOBARCH=x86_64 ;; esac \
    && curl -fsSL -o /tmp/gobuster.tar.gz \
        "https://github.com/OJ/gobuster/releases/download/v3.6.0/gobuster_Linux_${GOBARCH}.tar.gz" \
    && tar -xzf /tmp/gobuster.tar.gz -C /usr/local/bin gobuster \
    && rm /tmp/gobuster.tar.gz \
    && chmod +x /usr/local/bin/gobuster \
    # nikto is not packaged in Debian trixie — install from source with a
    # `nikto` wrapper on PATH so the exploit tool can call it uniformly.
    && curl -fsSL -o /tmp/nikto.tar.gz \
        "https://github.com/sullo/nikto/archive/refs/tags/2.5.0.tar.gz" \
    && mkdir -p /opt/nikto \
    && tar -xzf /tmp/nikto.tar.gz -C /opt/nikto --strip-components=1 \
    && rm /tmp/nikto.tar.gz \
    && printf '#!/bin/sh\nexec perl /opt/nikto/program/nikto.pl "$@"\n' > /usr/local/bin/nikto \
    && chmod +x /usr/local/bin/nikto

# Copy pre-built Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Run as non-root for security
RUN useradd -m -r appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

# Uvicorn with 2 workers — scale via container replicas in production
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]
