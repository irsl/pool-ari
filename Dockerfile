FROM alpine
WORKDIR /opt
RUN apk add python3 py3-requests tzdata
ENV TZ=Europe/Budapest
RUN cp /usr/share/zoneinfo/Europe/Budapest /etc/localtime
ADD . /opt
ENTRYPOINT ["/opt/pool_ari.py"]
