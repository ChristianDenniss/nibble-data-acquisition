package adapter

import (
	"bytes"
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	ingestv2 "github.com/ChristianDenniss/platform-contracts/gen/ingest/v2"
)

// SkipBrowser runs the approved local Playwright session collector and sends
// its successful observations to the API's existing v2 ingest service.
type SkipBrowser struct {
	client ingestv2.IngestServiceClient
}

func NewSkipBrowser(client ingestv2.IngestServiceClient) SkipBrowser {
	return SkipBrowser{client: client}
}

type skipCollection struct {
	Results []skipObservation `json:"results"`
}

type skipObservation struct {
	TargetID         string          `json:"target_id"`
	Restaurant       string          `json:"restaurant"`
	ItemName         string          `json:"item_name"`
	PriceCents       int64           `json:"price_cents"`
	Currency         string          `json:"currency"`
	FulfillmentMode  string          `json:"fulfillment_mode"`
	DeliveryExecutor string          `json:"delivery_executor"`
	ObservedAt       string          `json:"observed_at"`
	SourceURL        string          `json:"source_url"`
	Status           string          `json:"status"`
	Candidates       []skipCandidate `json:"candidates"`
}

type skipCandidate struct {
	Name   string    `json:"name"`
	Prices []float64 `json:"prices"`
}

type skipTarget struct {
	ID         string
	Restaurant string
	Address    string
	Name       string
}

func (s SkipBrowser) Collect(ctx context.Context) error {
	root := env("SKIP_BROWSER_DIR", filepath.Join("tools", "skip-browser"))
	node := env("NODE_BIN", "node")
	script := filepath.Join(root, "src", "collect-prices.mjs")
	cmd := exec.CommandContext(ctx, node, script)
	cmd.Dir = root
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("run Skip browser collector: %w: %s", err, strings.TrimSpace(stderr.String()))
	}

	var collected skipCollection
	if err := json.Unmarshal(stdout.Bytes(), &collected); err != nil {
		return fmt.Errorf("decode Skip collector output: %w", err)
	}
	for _, result := range collected.Results {
		if result.Status != "collected" {
			fmt.Fprintf(os.Stderr, "Skip item %s: %s", result.TargetID, result.Status)
			for _, candidate := range result.Candidates {
				fmt.Fprintf(os.Stderr, "; candidate %q prices=%v", candidate.Name, candidate.Prices)
			}
			fmt.Fprintln(os.Stderr)
		}
	}
	targets, err := readSkipTargets(filepath.Join(root, "input", "skip-targets.csv"))
	if err != nil {
		return err
	}
	byID := make(map[string]skipTarget, len(targets))
	for _, target := range targets {
		byID[target.ID] = target
	}

	now := time.Now().UTC()
	runID := fmt.Sprintf("skip_%d", now.UnixNano())
	if _, err := s.client.RecordChannel(ctx, &ingestv2.RecordChannelRequest{Channel: &ingestv2.Channel{
		Id: "ch_skip", Slug: "skip", Kind: "aggregator", Name: "Skip",
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordIngestRun(ctx, &ingestv2.RecordIngestRunRequest{Run: &ingestv2.IngestRun{
		Id: runID, JobType: "skip_browser_collection", ChannelId: "ch_skip",
		StartedAtUnixMs: now.UnixMilli(), ParserVersion: "skip_browser_v1",
	}}); err != nil {
		return err
	}

	registered := map[string]bool{}
	for _, obs := range collected.Results {
		if obs.Status != "collected" || obs.PriceCents < 0 {
			continue
		}
		target, ok := byID[obs.TargetID]
		if !ok {
			return fmt.Errorf("collector returned unknown target %q", obs.TargetID)
		}
		key := strings.ToLower(target.ID[:2])
		ids := skipIDs(key, target.ID)
		if !registered[key] {
			if err := s.registerRestaurant(ctx, target, ids); err != nil {
				return err
			}
			registered[key] = true
		} else if err := s.registerItem(ctx, target, ids); err != nil {
			return err
		}
		observedAt := now
		if parsed, err := time.Parse(time.RFC3339Nano, obs.ObservedAt); err == nil {
			observedAt = parsed
		}
		rawSnapshot, err := json.Marshal(obs)
		if err != nil {
			return fmt.Errorf("encode source snapshot for %s: %w", target.ID, err)
		}
		if _, err := s.client.RecordSourceSnapshot(ctx, &ingestv2.RecordSourceSnapshotRequest{
			Snapshot: &ingestv2.SourceSnapshot{
				Id:          fmt.Sprintf("snap_%s_%d", strings.ToLower(target.ID), now.UnixNano()),
				IngestRunId: runID, ExternalStoreId: ids.store, ContentType: "application/json",
				RawJson: rawSnapshot, ObservedAtUnixMs: observedAt.UnixMilli(),
			},
		}); err != nil {
			return fmt.Errorf("record source metadata for %s: %w", target.ID, err)
		}
		if _, err := s.client.RecordItemPriceObservation(ctx, &ingestv2.RecordItemPriceObservationRequest{
			Observation: &ingestv2.ItemPriceObservation{
				Id:           fmt.Sprintf("ipo_%s_%d", strings.ToLower(target.ID), now.UnixNano()),
				SourceItemId: ids.sourceItem, IngestRunId: runID,
				Price:            &ingestv2.Money{AmountCents: obs.PriceCents, Currency: defaultString(obs.Currency, "CAD")},
				FulfillmentMode:  defaultString(obs.FulfillmentMode, "delivery"),
				DeliveryExecutor: defaultString(obs.DeliveryExecutor, "third_party"),
				ObservedAtUnixMs: observedAt.UnixMilli(),
			},
		}); err != nil {
			return fmt.Errorf("record price for %s: %w", target.ID, err)
		}
	}

	collectedCount := 0
	for _, result := range collected.Results {
		if result.Status == "collected" {
			collectedCount++
		}
	}
	if collectedCount == 0 {
		return fmt.Errorf("Skip collector returned no unambiguous prices; check the saved login, delivery address, and item matches")
	}
	fmt.Fprintf(os.Stderr, "Skip browser collection ingested %d of %d target prices; ambiguous or missing items were not stored\n", collectedCount, len(targets))
	return nil
}

type skipRecordIDs struct {
	brand, place, store, option, menu, category, dish, sourceItem, itemMatch string
}

func skipIDs(branch, targetID string) skipRecordIDs {
	item := strings.ToLower(strings.ReplaceAll(targetID, "-", "_"))
	return skipRecordIDs{
		brand: "br_skip_" + branch, place: "pl_skip_" + branch, store: "ss_skip_" + branch,
		option: "ppo_skip_" + branch, menu: "menu_skip_" + branch, category: "cat_skip_" + branch,
		dish: "dish_" + item, sourceItem: "si_skip_" + item, itemMatch: "im_skip_" + item,
	}
}

func (s SkipBrowser) registerRestaurant(ctx context.Context, target skipTarget, ids skipRecordIDs) error {
	if _, err := s.client.RecordBrand(ctx, &ingestv2.RecordBrandRequest{Brand: &ingestv2.Brand{
		Id: ids.brand, Slug: strings.ToLower(strings.ReplaceAll(target.Restaurant, " ", "-")), Name: target.Restaurant,
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordPlace(ctx, &ingestv2.RecordPlaceRequest{Place: &ingestv2.Place{
		Id: ids.place, BrandId: ids.brand, Name: target.Restaurant,
		Location: &ingestv2.Location{Address: target.Address, City: "Fredericton", Region: "NB"},
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordSourceStore(ctx, &ingestv2.RecordSourceStoreRequest{Store: &ingestv2.SourceStore{
		Id: ids.store, ChannelId: "ch_skip", ExternalStoreId: ids.store, Name: target.Restaurant,
		Location: &ingestv2.Location{Address: target.Address, City: "Fredericton", Region: "NB"},
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordPurchaseOption(ctx, &ingestv2.RecordPurchaseOptionRequest{Option: &ingestv2.PurchaseOption{
		Id: ids.option, PlaceId: ids.place, ChannelId: "ch_skip", FulfillmentMode: "delivery",
		DeliveryExecutor: "third_party", SourceStoreId: ids.store,
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordSourceMenu(ctx, &ingestv2.RecordSourceMenuRequest{Menu: &ingestv2.SourceMenu{
		Id: ids.menu, SourceStoreId: ids.store, FulfillmentMode: "delivery", DeliveryExecutor: "third_party",
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordSourceCategory(ctx, &ingestv2.RecordSourceCategoryRequest{Category: &ingestv2.SourceCategory{
		Id: ids.category, SourceMenuId: ids.menu, Name: "Menu",
	}}); err != nil {
		return err
	}
	return s.registerItem(ctx, target, ids)
}

func (s SkipBrowser) registerItem(ctx context.Context, target skipTarget, ids skipRecordIDs) error {
	if _, err := s.client.RecordDish(ctx, &ingestv2.RecordDishRequest{Dish: &ingestv2.Dish{
		Id: ids.dish, BrandId: ids.brand, Name: target.Name,
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordSourceItem(ctx, &ingestv2.RecordSourceItemRequest{Item: &ingestv2.SourceItem{
		Id: ids.sourceItem, SourceCategoryId: ids.category, Name: target.Name, Available: true,
	}}); err != nil {
		return err
	}
	if _, err := s.client.RecordItemMatch(ctx, &ingestv2.RecordItemMatchRequest{Match: &ingestv2.ItemMatch{
		Id: ids.itemMatch, SourceItemId: ids.sourceItem, DishId: ids.dish, Confidence: 1,
		Status: "active", Method: "manual",
	}}); err != nil {
		return err
	}
	return nil
}

func readSkipTargets(path string) ([]skipTarget, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open Skip targets: %w", err)
	}
	defer f.Close()
	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("read Skip targets: %w", err)
	}
	if len(rows) < 2 {
		return nil, fmt.Errorf("Skip targets CSV has no rows")
	}
	columns := map[string]int{}
	for i, name := range rows[0] {
		columns[strings.TrimSpace(name)] = i
	}
	value := func(row []string, name string) string {
		i, ok := columns[name]
		if !ok || i >= len(row) {
			return ""
		}
		return strings.TrimSpace(row[i])
	}
	targets := make([]skipTarget, 0, len(rows)-1)
	for _, row := range rows[1:] {
		if len(row) == 0 {
			continue
		}
		t := skipTarget{ID: value(row, "id"), Restaurant: value(row, "restaurant"), Address: value(row, "branch_address"), Name: value(row, "search_name")}
		if t.ID != "" {
			targets = append(targets, t)
		}
	}
	return targets, nil
}

func env(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func defaultString(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}
