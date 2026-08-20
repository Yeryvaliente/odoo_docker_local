FROM public.ecr.aws/ubuntu/ubuntu:noble

SHELL ["/bin/bash", "-xo", "pipefail", "-c"]

# Generate locale C.UTF-8 for postgres and general locale data
ENV LANG=en_US.UTF-8

# Retrieve the target architecture to install the correct wkhtmltopdf package
ARG TARGETARCH

# Pick EC2 mirror by arch (ARM -> ports; x86 -> archive)
RUN set -eux; \
  arch="${TARGETARCH:-$(dpkg --print-architecture)}"; \
  if [ "$arch" = "arm64" ] || [ "$arch" = "armhf" ]; then \
    MIRROR="http://us-east-1.ec2.ports.ubuntu.com/ubuntu-ports/"; \
  else \
    MIRROR="http://us-east-1.ec2.archive.ubuntu.com/ubuntu/"; \
  fi; \
  sed -i -E "s|^URIs: .*|URIs: ${MIRROR}|" /etc/apt/sources.list.d/ubuntu.sources;

# Install development dependencies and debugging tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        dirmngr \
        fonts-noto-cjk \
        fonts-liberation \
        fonts-dejavu-core \
        gsfonts \
        gnupg \
        libssl-dev \
        node-less \
        npm \
        python3-numpy \
        python3-magic \
        python3-num2words \
        python3-odf \
        python3-pdfminer \
        python3-pip \
        python3-phonenumbers \
        python3-pyldap \
        python3-qrcode \
        python3-renderpm \
        python3-setuptools \
        python3-slugify \
        python3-vobject \
        python3-watchdog \
        python3-xlrd \
        python3-xlwt \
        xz-utils \
        # PDF compression dependencies
        qpdf \
        # Development tools
        git \
        vim \
        nano \
        htop \
        less \
        iputils-ping \
        telnet \
        postgresql-client \
        python3-dev \
        python3-venv \
        build-essential && \
    if [ -z "${TARGETARCH}" ]; then \
        TARGETARCH="$(dpkg --print-architecture)"; \
    fi; \
    echo "TARGETARCH is set to: ${TARGETARCH}" && \
    WKHTMLTOPDF_ARCH=${TARGETARCH} && \
    case ${TARGETARCH} in \
    "amd64") WKHTMLTOPDF_ARCH=amd64 && WKHTMLTOPDF_SHA=967390a759707337b46d1c02452e2bb6b2dc6d59  ;; \
    "arm64")  WKHTMLTOPDF_SHA=90f6e69896d51ef77339d3f3a20f8582bdf496cc  ;; \
    "ppc64le" | "ppc64el") WKHTMLTOPDF_ARCH=ppc64el && WKHTMLTOPDF_SHA=5312d7d34a25b321282929df82e3574319aed25c  ;; \
    esac \
    && curl -o wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.jammy_${WKHTMLTOPDF_ARCH}.deb \
    && echo ${WKHTMLTOPDF_SHA} wkhtmltox.deb | sha1sum -c - \
    && apt-get install -y --no-install-recommends ./wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* wkhtmltox.deb

# Install rtlcss
RUN npm install -g rtlcss

# Copy the GeoLite2 database
RUN mkdir -p /usr/share/GeoIP && \
    curl -o /tmp/GeoLite2-City.mmdb.gz -SL https://cdn.jsdelivr.net/npm/geolite2-city/GeoLite2-City.mmdb.gz && \
    gunzip /tmp/GeoLite2-City.mmdb.gz && \
    mv /tmp/GeoLite2-City.mmdb /usr/share/GeoIP/ && \
    rm -f /tmp/GeoLite2-City.mmdb

# Install Odoo
# Original version from external repository
ADD https://external-resources-techrrific.s3.us-east-1.amazonaws.com/odoo/odoo_18.0.e.20260413_all.deb /tmp/odoo.deb
# Local .deb file for testing (commented - use for local development)
# COPY ./odoo_18.0+e.20260218_all.deb /tmp/odoo.deb

RUN apt-get update \
    && apt-get -y install --no-install-recommends /tmp/odoo.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/odoo.deb

# Copy requirements file
COPY ./requirements.txt /tmp/requirements.txt

# Install Python packages from requirements.txt
RUN python3 -m pip install --break-system-packages --no-cache-dir --ignore-installed \
    -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Create directories for logs and debugging
RUN mkdir -p /var/log/odoo && \
    chown -R odoo:odoo /var/log/odoo

# Copy entrypoint script and wait script
COPY ./entrypoint.sh /entrypoint.sh
COPY ./wait-for-psql.py /usr/local/bin/wait-for-psql.py

# Make scripts executable
RUN chmod +x /entrypoint.sh /usr/local/bin/wait-for-psql.py

# Set permissions for odoo user
RUN chown odoo:odoo /entrypoint.sh

# Create development addons directory
RUN mkdir -p /mnt/extra-addons && \
    chown -R odoo:odoo /mnt/extra-addons

# Mount points for development
VOLUME ["/var/lib/odoo", "/mnt/extra-addons", "/var/log/odoo"]

# Expose Odoo services and debugging port
EXPOSE 8069 8071 8072 5678

# Set the default config file
ENV ODOO_RC=/etc/odoo/odoo.conf

# Set default user when running the container
USER odoo

ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]