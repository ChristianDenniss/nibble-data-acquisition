package adapter

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/ChristianDenniss/data-acquisition/internal/seed"
	ingestv2 "github.com/ChristianDenniss/platform-contracts/gen/ingest/v2"
)

const parserCurated = "curated_seed_v1"

type Curated struct {
	client ingestv2.IngestServiceClient
}

func NewCurated(client ingestv2.IngestServiceClient) Curated {
	return Curated{client: client}
}

func (c Curated) Collect(ctx context.Context) error {
	log.Printf("adapter: curated seed starting")
	now := time.Now().UTC()
	runID := "ingest_curated_" + now.Format("20060102T150405")

	if _, err := c.client.RecordIngestRun(ctx, &ingestv2.RecordIngestRunRequest{
		Run: &ingestv2.IngestRun{
			Id: runID, JobType: "curated_seed", StartedAtUnixMs: now.UnixMilli(),
			ParserVersion: parserCurated,
		},
	}); err != nil {
		return fmt.Errorf("ingest run: %w", err)
	}

	for _, ch := range seed.GlobalChannels() {
		if _, err := c.client.RecordChannel(ctx, &ingestv2.RecordChannelRequest{
			Channel: &ingestv2.Channel{Id: ch.ID, Slug: ch.Slug, Kind: ch.Kind, Name: ch.Name},
		}); err != nil {
			return fmt.Errorf("channel %s: %w", ch.Slug, err)
		}
	}

	for _, mp := range seed.MembershipProducts() {
		if _, err := c.client.RecordMembershipProduct(ctx, &ingestv2.RecordMembershipProductRequest{
			Product: &ingestv2.MembershipProduct{Id: mp.ID, ChannelId: mp.ChannelID, Name: mp.Name, Slug: mp.Slug},
		}); err != nil {
			return fmt.Errorf("membership %s: %w", mp.Slug, err)
		}
	}

	payload, err := json.Marshal(seed.Markets())
	if err != nil {
		return err
	}
	sum := sha256.Sum256(payload)
	if _, err := c.client.RecordSourceSnapshot(ctx, &ingestv2.RecordSourceSnapshotRequest{
		Snapshot: &ingestv2.SourceSnapshot{
			Id: "snap_curated_" + now.Format("20060102T150405"), IngestRunId: runID,
			ContentType: "application/json", RawJson: payload, Checksum: hex.EncodeToString(sum[:]),
			ObservedAtUnixMs: now.UnixMilli(),
		},
	}); err != nil {
		return fmt.Errorf("snapshot: %w", err)
	}

	for _, bundle := range seed.Markets() {
		m := bundle.Market
		if _, err := c.client.RecordMarket(ctx, &ingestv2.RecordMarketRequest{
			Market: &ingestv2.Market{
				Id: m.ID, Slug: m.Slug, Name: m.Name, Country: m.Country, Region: m.Region,
				Currency: m.Currency, Timezone: m.Timezone, Status: m.Status, GeohashPrefixes: m.GeohashPrefixes,
			},
		}); err != nil {
			return fmt.Errorf("market %s: %w", m.Slug, err)
		}
		for _, d := range bundle.Dropoffs {
			if _, err := c.client.RecordProbeDropoff(ctx, &ingestv2.RecordProbeDropoffRequest{
				Dropoff: &ingestv2.ProbeDropoff{
					Id: d.ID, MarketId: d.MarketID, Label: d.Label, Geohash: d.Geohash,
					Location: &ingestv2.Location{
						Latitude: d.Location.Latitude, Longitude: d.Location.Longitude,
						Address: d.Location.Address, City: d.Location.City,
						Region: d.Location.Region, PostalCode: d.Location.PostalCode,
					},
				},
			}); err != nil {
				return fmt.Errorf("dropoff %s: %w", d.ID, err)
			}
		}
		for _, cov := range bundle.Coverage {
			if _, err := c.client.RecordChannelMarketCoverage(ctx, &ingestv2.RecordChannelMarketCoverageRequest{
				Coverage: &ingestv2.ChannelMarketCoverage{
					Id: cov.ID, ChannelId: cov.ChannelID, MarketId: m.ID,
					Status: cov.Status, Note: cov.Note,
				},
			}); err != nil {
				return fmt.Errorf("coverage %s: %w", cov.ID, err)
			}
		}
	}

	if err := IngestCompareCatalog(ctx, c.client, runID, now); err != nil {
		return fmt.Errorf("compare catalog: %w", err)
	}

	finished := time.Now().UTC()
	if _, err := c.client.RecordIngestRun(ctx, &ingestv2.RecordIngestRunRequest{
		Run: &ingestv2.IngestRun{
			Id: runID, JobType: "curated_seed", StartedAtUnixMs: now.UnixMilli(),
			FinishedAtUnixMs: finished.UnixMilli(), ParserVersion: parserCurated,
		},
	}); err != nil {
		return fmt.Errorf("finish run: %w", err)
	}

	log.Printf("adapter: curated seed complete (fredericton markets + compare catalog)")
	return nil
}
