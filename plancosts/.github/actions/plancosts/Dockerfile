FROM alpine:3.19

# Versions
ENV TERRAFORM_VERSION=1.7.5

# System deps
RUN apk --no-cache add \
    bash curl jq git python3 py3-pip ca-certificates unzip

# Terraform (needed when running against a tf directory)
RUN wget -O /tmp/terraform.zip "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
 && unzip /tmp/terraform.zip -d /usr/local/bin \
 && rm -f /tmp/terraform.zip

# Python deps: install your tool (expects requirements.txt at repo root)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt || true

# Copy repo (action workspace is mounted at /github/workspace by Actions)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
