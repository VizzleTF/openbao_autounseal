FROM python:3.9-slim AS build-env
LABEL description='OpenBaoauto-unseal for Kubernetes'
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1
ENV PYTHONUNBUFFERED 1
COPY ./ /app
WORKDIR app
RUN pip install --no-cache-dir --upgrade -r requirements.txt  && rm -rf requirements.txt

FROM gcr.io/distroless/python3:nonroot
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH=/usr/local/lib/python3.9/site-packages
ENV OPENBAO_URL ""
ENV OPENBAO_SECRET_SHARES ""
ENV OPENBAO_SECRET_THRESHOLD ""
ENV NAMESPACE ""
ENV OPENBAO_ROOT_TOKEN_SECRET ""
ENV OPENBAO_KEYS_SECRET ""
ENV PYTHONWARNINGS "ignore:Unverified HTTPS request"

COPY --from=build-env /app /app
COPY --from=build-env /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
WORKDIR /app
CMD ["/app/app.py"]
