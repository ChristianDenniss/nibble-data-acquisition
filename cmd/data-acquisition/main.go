package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ChristianDenniss/data-acquisition/internal/adapter"
	ingestv2 "github.com/ChristianDenniss/platform-contracts/gen/ingest/v2"
	"google.golang.org/grpc"
	"google.golang.org/grpc/connectivity"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lmicroseconds)
	addr := getenv("API_ENGINE_GRPC_ADDR", "localhost:9090")
	adapterName := getenv("ACQUISITION_ADAPTER", "demo")
	log.Printf("data-acquisition starting API_ENGINE_GRPC_ADDR=%s ACQUISITION_ADAPTER=%s", addr, adapterName)

	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("grpc client: %v", err)
	}
	defer conn.Close()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	log.Printf("waiting for api-engine gRPC at %s", addr)
	if err := waitReady(ctx, conn); err != nil {
		log.Fatalf("api-engine grpc: %v", err)
	}

	var coll adapter.Adapter
	switch adapterName {
	case "demo":
		coll = adapter.NewDemoFixture(ingestv2.NewIngestServiceClient(conn))
	case "skip":
		coll = adapter.NewSkipBrowser(ingestv2.NewIngestServiceClient(conn))
	case "stub":
		coll = adapter.Stub{}
	default:
		log.Fatalf("unknown ACQUISITION_ADAPTER=%q (use demo, skip, or stub)", adapterName)
	}

	if err := coll.Collect(ctx); err != nil {
		if adapterName != "skip" {
			log.Fatalf("collect: %v", err)
		}
		log.Printf("initial Skip collection failed; will retry on the configured interval: %v", err)
	}

	if adapterName == "skip" {
		interval, err := time.ParseDuration(getenv("SKIP_COLLECTION_INTERVAL", "15m"))
		if err != nil || interval <= 0 {
			log.Fatalf("invalid SKIP_COLLECTION_INTERVAL; use a positive duration such as 15m")
		}
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		log.Printf("Skip backend collection enabled; refreshing every %s", interval)
		for {
			select {
			case <-ctx.Done():
				log.Printf("data-acquisition stopping")
				return
			case <-ticker.C:
				if err := coll.Collect(ctx); err != nil {
					log.Printf("Skip collection failed: %v", err)
				}
			}
		}
	}

	log.Printf("data-acquisition collect finished; idle until signal")
	<-ctx.Done()
	log.Printf("data-acquisition stopping")
}

func waitReady(ctx context.Context, conn *grpc.ClientConn) error {
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	conn.Connect()
	for {
		state := conn.GetState()
		log.Printf("grpc state: %s", state)
		if state == connectivity.Ready {
			log.Printf("grpc ready")
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
