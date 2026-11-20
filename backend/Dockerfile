FROM golang:1.24-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /university-agent ./cmd/university-agent

FROM alpine:3.21
RUN apk add --no-cache ca-certificates && adduser -D -H app
USER app
COPY --from=builder /university-agent /usr/local/bin/university-agent
EXPOSE 8080
ENTRYPOINT ["university-agent"]
