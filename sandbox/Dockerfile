FROM ubuntu:22.04

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    bubblewrap \
    libseccomp-dev \
    libcap-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy source
WORKDIR /app
COPY supervisor.py .
COPY exec_harness.c .
COPY seccomp_allow.txt .
COPY landlock_ruleset.json .
COPY run_supervisor.sh .

# Build seccomp BPF from the allow-list
RUN scmp syscall -d seccomp_allow.txt > /etc/seccomp/default.bin

# Build exec_harness
RUN gcc -Wall -O2 -o /opt/exec_harness exec_harness.c -lcap

# Make supervisor executable
RUN chmod +x run_supervisor.sh

# Expose the gRPC port (optional – you can also use a UNIX socket for the frontend)
EXPOSE 50051

CMD ["./run_supervisor.sh"]