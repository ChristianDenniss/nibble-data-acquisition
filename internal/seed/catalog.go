package seed

// Catalog seed lives here so collectors do not import go-data-model.

type Channel struct {
	ID   string
	Slug string
	Kind string
	Name string
}

type Location struct {
	Latitude   float64
	Longitude  float64
	Address    string
	City       string
	Region     string
	PostalCode string
}

type Market struct {
	ID              string
	Slug            string
	Name            string
	Country         string
	Region          string
	Currency        string
	Timezone        string
	Status          string
	GeohashPrefixes string
}

type ProbeDropoff struct {
	ID       string
	MarketID string
	Label    string
	Geohash  string
	Location Location
}

type ExpectedCoverage struct {
	ID        string
	ChannelID string
	Status    string
	Note      string
}

type MembershipProduct struct {
	ID        string
	ChannelID string
	Name      string
	Slug      string
}

type MarketBundle struct {
	Market   Market
	Dropoffs []ProbeDropoff
	Coverage []ExpectedCoverage
}

const (
	CoverageExpected = "expected"
	CoverageObserved = "observed"
	CoverageAbsent   = "absent"
	CoverageUnknown  = "unknown"
	MarketActive     = "active"
)

func GlobalChannels() []Channel {
	return []Channel{
		{ID: "ch_skip", Slug: "skip", Kind: "aggregator", Name: "SkipTheDishes"},
		{ID: "ch_doordash", Slug: "doordash", Kind: "aggregator", Name: "DoorDash"},
		{ID: "ch_ubereats", Slug: "ubereats", Kind: "aggregator", Name: "Uber Eats"},
		{ID: "ch_instacart", Slug: "instacart", Kind: "aggregator", Name: "Instacart"},
		{ID: "ch_grubhub", Slug: "grubhub", Kind: "aggregator", Name: "Grubhub"},
		{ID: "ch_fantuan", Slug: "fantuan", Kind: "aggregator", Name: "Fantuan"},
		{ID: "ch_merchant_web", Slug: "merchant-web", Kind: "merchant_web", Name: "Merchant website"},
		{ID: "ch_phone", Slug: "phone", Kind: "phone", Name: "Phone order"},
		{ID: "ch_in_person", Slug: "in-person", Kind: "in_person", Name: "In person"},
	}
}

func MembershipProducts() []MembershipProduct {
	return []MembershipProduct{
		{ID: "mp_dashpass", ChannelID: "ch_doordash", Name: "DashPass", Slug: "dashpass"},
		{ID: "mp_uber_one", ChannelID: "ch_ubereats", Name: "Uber One", Slug: "uber-one"},
		{ID: "mp_skip_plus", ChannelID: "ch_skip", Name: "Skip+", Slug: "skip-plus"},
		{ID: "mp_instacart_plus", ChannelID: "ch_instacart", Name: "Instacart+", Slug: "instacart-plus"},
		{ID: "mp_grubhub_plus", ChannelID: "ch_grubhub", Name: "Grubhub+", Slug: "grubhub-plus"},
	}
}

func Fredericton() MarketBundle {
	const marketID = "mkt_fredericton"
	return MarketBundle{
		Market: Market{
			ID: marketID, Slug: "fredericton", Name: "Fredericton", Country: "CA", Region: "NB",
			Currency: "CAD", Timezone: "America/Moncton", Status: MarketActive,
			GeohashPrefixes: "f80t",
		},
		Dropoffs: []ProbeDropoff{
			{
				ID: "probe_frd_unbf", MarketID: marketID, Label: "UNBF campus", Geohash: "f80t7s",
				Location: Location{
					Latitude: 45.9458, Longitude: -66.6414,
					Address: "3 Bailey Dr", City: "Fredericton", Region: "NB", PostalCode: "E3B 5A3",
				},
			},
			{
				ID: "probe_frd_downtown", MarketID: marketID, Label: "Downtown", Geohash: "f80t7r",
				Location: Location{
					Latitude: 45.9636, Longitude: -66.6431,
					Address: "427 Queen St", City: "Fredericton", Region: "NB", PostalCode: "E3B 1B5",
				},
			},
			{
				ID: "probe_frd_regent", MarketID: marketID, Label: "Regent / uptown", Geohash: "f80t74",
				Location: Location{
					Latitude: 45.9369, Longitude: -66.6630,
					Address: "1381 Regent St", City: "Fredericton", Region: "NB", PostalCode: "E3C 1A2",
				},
			},
		},
		Coverage: []ExpectedCoverage{
			{ID: "cov_skip_fredericton", ChannelID: "ch_skip", Status: CoverageExpected, Note: "Skip operates in Fredericton"},
			{ID: "cov_doordash_fredericton", ChannelID: "ch_doordash", Status: CoverageExpected, Note: "DoorDash operates in Fredericton"},
			{ID: "cov_ubereats_fredericton", ChannelID: "ch_ubereats", Status: CoverageUnknown, Note: "Not confirmed in Fredericton yet"},
			{ID: "cov_instacart_fredericton", ChannelID: "ch_instacart", Status: CoverageUnknown, Note: "Not confirmed in Fredericton yet"},
			{ID: "cov_grubhub_fredericton", ChannelID: "ch_grubhub", Status: CoverageAbsent, Note: "Grubhub does not operate in Canada"},
			{ID: "cov_fantuan_fredericton", ChannelID: "ch_fantuan", Status: CoverageUnknown, Note: "Not confirmed in Fredericton yet"},
			{ID: "cov_in_person_fredericton", ChannelID: "ch_in_person", Status: CoverageExpected, Note: "Always available"},
			{ID: "cov_phone_fredericton", ChannelID: "ch_phone", Status: CoverageExpected, Note: "Always available"},
			{ID: "cov_merchant_web_fredericton", ChannelID: "ch_merchant_web", Status: CoverageExpected, Note: "Per kitchen, not market-wide"},
		},
	}
}

func Markets() []MarketBundle {
	return []MarketBundle{Fredericton()}
}
