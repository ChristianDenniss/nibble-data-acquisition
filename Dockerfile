# syntax=docker/dockerfile:1

FROM golang:1.23-alpine AS build
ARG GITHUB_TOKEN
WORKDIR /src
RUN apk add --no-cache git ca-certificates
ENV GOPRIVATE=github.com/ChristianDenniss/*
ENV GONOSUMDB=github.com/ChristianDenniss/*
RUN if [ -n "$GITHUB_TOKEN" ]; then \
  git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"; \
  fi
COPY go.mod go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod \
  go mod download
COPY cmd cmd
COPY internal internal
RUN --mount=type=cache,target=/go/pkg/mod \
  --mount=type=cache,target=/root/.cache/go-build \
  CGO_ENABLED=0 go build -mod=mod -trimpath -ldflags="-s -w" -o /out/data-acquisition ./cmd/data-acquisition

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /out/data-acquisition /usr/local/bin/data-acquisition
ENTRYPOINT ["data-acquisition"]
