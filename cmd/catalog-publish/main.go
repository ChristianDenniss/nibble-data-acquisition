// catalog-publish sends a versioned provider bundle over the private ingest API.
package main

import (
	"context"
	"crypto/sha256"
	"fmt"
	ingest "github.com/ChristianDenniss/platform-contracts/gen/ingest/v2"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"io"
	"log"
	"os"
	"time"
)

func main() {
	raw, err := io.ReadAll(io.LimitReader(os.Stdin, (16<<20)+1))
	if err != nil {
		log.Fatal(err)
	}
	if len(raw) > 16<<20 {
		log.Fatal("bundle exceeds 16 MiB")
	}
	addr := os.Getenv("API_ENGINE_GRPC_ADDR")
	if addr == "" {
		addr = "localhost:9090"
	}
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()), grpc.WithDefaultCallOptions(grpc.MaxCallSendMsgSize(16<<20)))
	if err != nil {
		log.Fatal(err)
	}
	defer conn.Close()
	checksum := fmt.Sprintf("%x", sha256.Sum256(raw))
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	_, err = ingest.NewIngestServiceClient(conn).RecordSourceSnapshot(ctx, &ingest.RecordSourceSnapshotRequest{Snapshot: &ingest.SourceSnapshot{Id: checksum, ContentType: "application/vnd.nibble.catalog.v1+json", RawJson: raw, Checksum: checksum}})
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("published catalog %s", checksum[:12])
}
