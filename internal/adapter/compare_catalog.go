package adapter

import (
	"context"
	"fmt"
	"time"

	ingestv2 "github.com/ChristianDenniss/platform-contracts/gen/ingest/v2"
)

// IngestCompareCatalog writes the Fredericton compare vertical slice (place, paths, menus, prices).
// Same shape as nibble-local-dev/scripts/seed_compare_demo.sql.
func IngestCompareCatalog(ctx context.Context, client ingestv2.IngestServiceClient, runID string, now time.Time) error {
	for _, ch := range []*ingestv2.Channel{
		{Id: "ch_skip", Slug: "skip", Kind: "aggregator", Name: "Skip"},
		{Id: "ch_store", Slug: "store", Kind: "merchant_app", Name: "Store app"},
	} {
		if _, err := client.RecordChannel(ctx, &ingestv2.RecordChannelRequest{Channel: ch}); err != nil {
			return fmt.Errorf("channel %s: %w", ch.Id, err)
		}
	}

	if _, err := client.RecordBrand(ctx, &ingestv2.RecordBrandRequest{
		Brand: &ingestv2.Brand{Id: "br_demo", Slug: "demo-burger", Name: "Demo Burger"},
	}); err != nil {
		return err
	}

	if _, err := client.RecordDish(ctx, &ingestv2.RecordDishRequest{
		Dish: &ingestv2.Dish{Id: "dish_burger", BrandId: "br_demo", Name: "Classic Burger", Description: "Demo canonical dish"},
	}); err != nil {
		return err
	}

	lat, lng := 45.9636, -66.6431
	for _, st := range []struct {
		id, ch, ext, name string
	}{
		{"ss_skip", "ch_skip", "ext-skip-1", "Demo via Skip"},
		{"ss_store", "ch_store", "ext-store-1", "Demo store direct"},
	} {
		if _, err := client.RecordSourceStore(ctx, &ingestv2.RecordSourceStoreRequest{
			Store: &ingestv2.SourceStore{
				Id: st.id, ChannelId: st.ch, ExternalStoreId: st.ext, Name: st.name,
				Location: &ingestv2.Location{Latitude: lat, Longitude: lng},
			},
		}); err != nil {
			return fmt.Errorf("store %s: %w", st.id, err)
		}
	}

	if _, err := client.RecordPlace(ctx, &ingestv2.RecordPlaceRequest{
		Place: &ingestv2.Place{
			Id: "pl_demo", BrandId: "br_demo", Name: "Demo Burger Queen St",
			Location: &ingestv2.Location{
				Latitude: lat, Longitude: lng, Address: "427 Queen St", City: "Fredericton", Region: "NB", PostalCode: "E3B 1B5",
			},
		},
	}); err != nil {
		return err
	}

	for _, opt := range []*ingestv2.PurchaseOption{
		{Id: "ppo_pickup", PlaceId: "pl_demo", ChannelId: "ch_store", FulfillmentMode: "pickup", SourceStoreId: "ss_store"},
		{Id: "ppo_3p", PlaceId: "pl_demo", ChannelId: "ch_skip", FulfillmentMode: "delivery", DeliveryExecutor: "third_party", SourceStoreId: "ss_skip"},
	} {
		if _, err := client.RecordPurchaseOption(ctx, &ingestv2.RecordPurchaseOptionRequest{Option: opt}); err != nil {
			return err
		}
	}

	for _, menu := range []*ingestv2.SourceMenu{
		{Id: "menu_store_pickup", SourceStoreId: "ss_store", FulfillmentMode: "pickup"},
		{Id: "menu_skip_del", SourceStoreId: "ss_skip", FulfillmentMode: "delivery", DeliveryExecutor: "third_party"},
	} {
		if _, err := client.RecordSourceMenu(ctx, &ingestv2.RecordSourceMenuRequest{Menu: menu}); err != nil {
			return err
		}
	}

	for _, cat := range []*ingestv2.SourceCategory{
		{Id: "cat_store", SourceMenuId: "menu_store_pickup", Name: "Mains"},
		{Id: "cat_skip", SourceMenuId: "menu_skip_del", Name: "Mains"},
	} {
		if _, err := client.RecordSourceCategory(ctx, &ingestv2.RecordSourceCategoryRequest{Category: cat}); err != nil {
			return err
		}
	}

	for _, item := range []*ingestv2.SourceItem{
		{Id: "si_store_burger", SourceCategoryId: "cat_store", Name: "Classic Burger"},
		{Id: "si_skip_burger", SourceCategoryId: "cat_skip", Name: "Classic Burger"},
	} {
		if _, err := client.RecordSourceItem(ctx, &ingestv2.RecordSourceItemRequest{Item: item}); err != nil {
			return err
		}
	}

	for _, m := range []*ingestv2.ItemMatch{
		{Id: "im_store", SourceItemId: "si_store_burger", DishId: "dish_burger", Confidence: 0.99, Status: "active", Method: "manual"},
		{Id: "im_skip", SourceItemId: "si_skip_burger", DishId: "dish_burger", Confidence: 0.99, Status: "active", Method: "manual"},
	} {
		if _, err := client.RecordItemMatch(ctx, &ingestv2.RecordItemMatchRequest{Match: m}); err != nil {
			return err
		}
	}

	obsAt := now.UnixMilli()
	for _, ipo := range []struct {
		id, item, mode, exec string
		cents                int64
	}{
		{"ipo_store", "si_store_burger", "pickup", "", 1200},
		{"ipo_skip", "si_skip_burger", "delivery", "third_party", 1350},
	} {
		if _, err := client.RecordItemPriceObservation(ctx, &ingestv2.RecordItemPriceObservationRequest{
			Observation: &ingestv2.ItemPriceObservation{
				Id: ipo.id, SourceItemId: ipo.item, IngestRunId: runID,
				Price: &ingestv2.Money{AmountCents: ipo.cents, Currency: "CAD"},
				FulfillmentMode: ipo.mode, DeliveryExecutor: ipo.exec, ObservedAtUnixMs: obsAt,
			},
		}); err != nil {
			return err
		}
	}

	if _, err := client.RecordQuoteObservation(ctx, &ingestv2.RecordQuoteObservationRequest{
		Observation: &ingestv2.QuoteObservation{
			Id: "qo_skip", SourceStoreId: "ss_skip", ChannelId: "ch_skip",
			FulfillmentMode: "delivery", DeliveryExecutor: "third_party", DropoffGeohash: "f80t7",
			MembershipTier: "", QuoteKind: "indicative", BasketSubtotalCents: 1000,
			ObservedAtUnixMs: obsAt, IngestRunId: runID,
			FeeLines: []*ingestv2.QuoteFeeLine{
				{Id: "qfl_del", Kind: "delivery", Amount: &ingestv2.Money{AmountCents: 399, Currency: "CAD"}},
				{Id: "qfl_svc", Kind: "service", Amount: &ingestv2.Money{AmountCents: 199, Currency: "CAD"}},
			},
		},
	}); err != nil {
		return err
	}

	return nil
}
