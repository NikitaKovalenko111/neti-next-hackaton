FROM golang:1.24-alpine AS builder

ARG MINIO_VERSION=RELEASE.2025-09-07T16-13-09Z
RUN apk add --no-cache git
RUN git clone --depth 1 --branch "$MINIO_VERSION" https://github.com/minio/minio.git /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/minio .

FROM alpine:3.21
RUN apk add --no-cache ca-certificates curl && adduser -D minio \
    && mkdir /data && chown minio:minio /data
COPY --from=builder /out/minio /usr/local/bin/minio
COPY --from=builder /src/LICENSE /licenses/minio/LICENSE
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
