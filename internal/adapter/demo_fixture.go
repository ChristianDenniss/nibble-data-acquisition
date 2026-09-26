package adapter

import (
	"context"
	"log"
	"time"

	ingestv2 "github.com/ChristianDenniss/platform-contracts/gen/ingest/v2"
)

// DemoFixture loads the compare catalog via ingest v2 (legacy adapter name).
type DemoFixture struct {
	client ingestv2.IngestServiceClient
}

func NewDemoFixture(client ingestv2.IngestServiceClient) DemoFixture {
	return DemoFixture{client: client}
}

func (d DemoFixture) Collect(ctx context.Context) error {
	log.Printf("adapter: demo fixture ingest starting")
	now := time.Now().UTC()
	runID := "ingest_demo_" + now.Format("20060102T150405")

	if _, err := d.client.RecordIngestRun(ctx, &ingestv2.RecordIngestRunRequest{
		Run: &ingestv2.IngestRun{
			Id: runID, JobType: "demo_fixture", StartedAtUnixMs: now.UnixMilli(),
			ParserVersion: "demo_fixture_v1",
		},
	}); err != nil {
		return err
	}

	if err := IngestCompareCatalog(ctx, d.client, runID, now); err != nil {
		return err
	}

	log.Printf("adapter: demo fixture ingest complete (place pl_demo, dish dish_burger)")
	return nil
}
