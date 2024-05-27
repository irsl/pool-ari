FROM alpine
WORKDIR /opt
RUN apk add python3 py3-requests
ADD . /opt
ENTRYPOINT ["/opt/pool_ari.py"]
