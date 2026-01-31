FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -u 1000 researcher
USER researcher
WORKDIR /home/researcher/workspace

# Install common python libraries
# We use --user to install to /home/researcher/.local
RUN pip install --no-cache-dir --user \
    numpy \
    pandas \
    scipy \
    matplotlib \
    seaborn \
    scikit-learn \
    tqdm \
    requests

# Add local bin to PATH
ENV PATH="/home/researcher/.local/bin:${PATH}"

# Default command
CMD ["python3"]
