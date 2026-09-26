FROM golang:1.23-bookworm AS build
ARG GITHUB_TOKEN
WORKDIR /src
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git >/dev/null
ENV GOPRIVATE=github.com/ChristianDenniss/*
ENV GONOSUMDB=github.com/ChristianDenniss/*
RUN if [ -n "$GITHUB_TOKEN" ]; then \
  git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"; \
  fi
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/data-acquisition ./cmd/data-acquisition

FROM debian:bookworm-slim
COPY --from=build /out/data-acquisition /usr/local/bin/data-acquisition
ENTRYPOINT ["data-acquisition"]
