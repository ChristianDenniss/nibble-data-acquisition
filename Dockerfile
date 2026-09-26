FROM golang:1.23-bookworm AS build
WORKDIR /src
COPY platform-contracts ./platform-contracts
COPY data-acquisition ./data-acquisition
RUN printf 'go 1.23\n\nuse (\n\t./platform-contracts\n\t./data-acquisition\n)\n' > go.work
WORKDIR /src/data-acquisition
RUN GOWORK=/src/go.work go mod tidy && CGO_ENABLED=0 GOWORK=/src/go.work go build -o /out/data-acquisition ./cmd/data-acquisition

FROM debian:bookworm-slim
COPY --from=build /out/data-acquisition /usr/local/bin/data-acquisition
ENTRYPOINT ["data-acquisition"]
