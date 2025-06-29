FROM ubuntu:22.04

# Install minimal dependencies first
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    ca-certificates \
    lsb-release \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Java 22 from adoptium
RUN wget -q -O - https://packages.adoptium.net/artifactory/api/gpg/key/public | apt-key add - && \
    echo "deb https://packages.adoptium.net/artifactory/deb $(lsb_release -cs) main" > /etc/apt/sources.list.d/adoptium.list && \
    apt-get update && \
    apt-get install -y temurin-22-jdk && \
    rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME
ENV JAVA_HOME=/usr/lib/jvm/temurin-22-jdk-arm64
ENV PATH=$JAVA_HOME/bin:$PATH

# Create working directory
WORKDIR /workspace

# Copy install script
COPY ../install-alchitry-labs.sh /tmp/install-alchitry-labs.sh
RUN chmod +x /tmp/install-alchitry-labs.sh

# Install Alchitry Labs
RUN /tmp/install-alchitry-labs.sh

# Create a wrapper script to run Alchitry Labs CLI with system Java
RUN echo '#!/bin/bash\njava -Dapp.dir="/root/alchitry-labs/alchitry-labs-2.0.36" -cp "/root/alchitry-labs/alchitry-labs-2.0.36/lib/app/*" com.alchitry.labs2.CLIKt "$@"' > /usr/local/bin/alchitry && \
    chmod +x /usr/local/bin/alchitry

# Set up environment variables for Alchitry Labs
ENV ALCHITRY_BIN=/usr/local/bin/alchitry
ENV PATH=$PATH:/usr/local/bin

# Default command
CMD ["/bin/bash"]