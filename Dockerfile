FROM python:3.13-slim AS build-env
LABEL description="OpenBao auto-unseal for Kubernetes"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1
COPY ./ /app
WORKDIR /app
RUN pip install --no-cache-dir --upgrade -r requirements.txt && rm -rf requirements.txt

# debian13 distroless ships Python 3.13 — must match the build-stage interpreter
# (site-packages are version-pathed). Pinning the debian13 variant keeps runtime
# Python at 3.13 instead of the floating `python3` tag, so the 3.13 site-packages
# copied below always match the interpreter (a version skew here crashlooped 0.5.4).
FROM gcr.io/distroless/python3-debian13:nonroot
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/usr/local/lib/python3.13/site-packages \
    PYTHONWARNINGS="ignore:Unverified HTTPS request"
COPY --from=build-env /app /app
COPY --from=build-env /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
WORKDIR /app
CMD ["/app/app.py"]
