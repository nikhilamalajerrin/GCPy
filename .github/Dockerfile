# -------- Stage 1: builder (installs deps + terraform) --------
    FROM python:3.11-slim AS builder

    ARG TERRAFORM_VERSION=0.12.25
    ARG ARCH=linux
    
    ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1
    
    # System deps for Terraform + build
    RUN apt-get update && apt-get install -y --no-install-recommends \
          curl unzip ca-certificates build-essential git \
        && rm -rf /var/lib/apt/lists/*
    
    # Install Terraform (to support --tfdir/--tfplan flow; for --tfjson you can ignore)
    RUN curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_${ARCH}_amd64.zip" -o /tmp/terraform.zip \
        && unzip /tmp/terraform.zip -d /usr/local/bin \
        && chmod +x /usr/local/bin/terraform \
        && rm -f /tmp/terraform.zip
    
    WORKDIR /app
    
    # If you have a requirements.txt, use it for layer caching first
    # (If you use Poetry or a pyproject, replace these two COPY/RUN blocks accordingly)
    COPY requirements.txt /app/requirements.txt
    RUN pip install --no-cache-dir -r requirements.txt || true
    
    # Install the package
    COPY . /app
    RUN pip install --no-cache-dir .
    
    # -------- Stage 2: runtime image --------
    FROM python:3.11-slim AS app
    
    ARG TERRAFORM_VERSION=0.12.25
    
    ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        # default pricing endpoint; can be overridden at runtime
        PLANCOSTS_API_URL="http://127.0.0.1:4000/graphql"
    
    # Bring in terraform from builder (binary already installed there)
    COPY --from=builder /usr/local/bin/terraform /usr/local/bin/terraform
    
    # Copy site-packages and scripts from builder
    COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
    COPY --from=builder /usr/local/bin /usr/local/bin
    
    WORKDIR /root
    
    # Default to showing help; you can override with `docker run ... --tfjson ...`
    ENTRYPOINT ["python", "-m", "plancosts.main"]
    CMD ["--help"]
    