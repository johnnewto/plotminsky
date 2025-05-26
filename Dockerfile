FROM ubuntu:24.04

# Set non-interactive frontend for apt to avoid prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install essential dependencies for Minsky and pyminsky
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    python3 \
    python3-pip \
    python3-venv \
    python3-full \
    tcl \
    tk \
    libboost-all-dev \
    librsvg2-2 \
    libgsl-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libreadline-dev \
    xclip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Add the OpenSUSE repository for Minsky (Ubuntu 24.04)
RUN echo 'deb http://download.opensuse.org/repositories/home:/hpcoder1/xUbuntu_24.04/ /' | tee /etc/apt/sources.list.d/home:hpcoder1.list \
    && curl -fsSL https://download.opensuse.org/repositories/home:hpcoder1/xUbuntu_24.04/Release.key | gpg --dearmor | tee /etc/apt/trusted.gpg.d/home_hpcoder1.gpg > /dev/null

# Update package lists and install Minsky
RUN apt-get update && apt-get install -y minsky \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create and activate virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements.txt and install Python dependencies in virtual environment
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn[standard]

# Set PYTHONPATH to include the directory containing pyminsky.so
ENV PYTHONPATH=/usr/local/lib/python3.12/dist-packages:$PYTHONPATH

# Create assets directory for custom CSS
RUN mkdir -p /app/assets

# Copy application files
COPY main.py .
COPY app_dash1.py .
COPY config.json .
COPY BOMDwithGovernmentLive.mky .
# COPY assets/custom.css /app/assets/



# Verify pyminsky is available by importing it in Python
RUN python3 -c "import pyminsky; print('pyminsky imported successfully')"

# # Create a non-root user for running the application
# RUN useradd -m appuser
# USER appuser

# Set the working directory for the application
WORKDIR /app

# Expose the port the app runs on
# EXPOSE 8050

# add a terminal entrypoint
# ENTRYPOINT ["/bin/bash"]

ENTRYPOINT ["uvicorn", "main:app", "--host=0.0.0.0", "--port=80"]