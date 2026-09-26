package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ChristianDenniss/data-acquisition/internal/adapter"
	ingestv1 "github.com/ChristianDenniss/platform-contracts/gen/ingest/v1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	addr := getenv("API_ENGINE_GRPC_ADDR", "localhost:9090")

	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("grpc client: %v", err)
	}
	defer conn.Close()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := waitReady(ctx, conn); err != nil {
		log.Fatalf("api-engine grpc: %v", err)
	}

	_ = ingestv1.NewIngestServiceClient(conn)
	stub := adapter.Stub{}
	if err := stub.Collect(ctx); err != nil {
		log.Fatalf("collect: %v", err)
	}

	log.Printf("connected to api-engine at %s; stub adapter collects nothing", addr)
	<-ctx.Done()
}

func waitReady(ctx context.Context, conn *grpc.ClientConn) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	conn.Connect()
	for {
		state := conn.GetState()
		if state == connectivity.Ready {
			return nil
		}
		if !conn.WaitForStateChange(ctx, state) {
			return ctx.Err()
		}
	}
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
