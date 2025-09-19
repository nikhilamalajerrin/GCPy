# .github/actions/plancosts/Dockerfile
FROM alpine:3.19

# GitHub container actions don't support build args, so use ENV
# so forks can tweak versions/paths by editing this file.
ENV TERRAFORM_VERSION=1.7.5 \
    TERRAFORM_BINARY=terraform \
    PYTHON_PIP_INDEX_URL= \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps
RUN apk --no-cache add \
      bash curl jq git python3 py3-pip ca-certificates unzip

# Terraform (name it using $TERRAFORM_BINARY to mirror the infracost commit idea)
RUN wget -O /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
 && unzip /tmp/terraform.zip -d /tmp \
 && mv /tmp/terraform "/usr/local/bin/${TERRAFORM_BINARY}" \
 && ln -s "/usr/local/bin/${TERRAFORM_BINARY}" /usr/local/bin/terraform \
 && rm -f /tmp/terraform.zip

# Python deps: install your tool (expects requirements.txt at repo root)
# If you don’t have one, this will just no-op (kept as-is for parity).
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt || true

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
