FROM golang:1.23-bookworm AS build
WORKDIR /src
COPY platform-contracts ./platform-contracts
COPY data-acquisition ./data-acquisition
WORKDIR /src/data-acquisition
RUN go mod tidy && CGO_ENABLED=0 go build -o /out/data-acquisition ./cmd/data-acquisition

FROM debian:bookworm-slim
COPY --from=build /out/data-acquisition /usr/local/bin/data-acquisition
ENTRYPOINT ["data-acquisition"]
