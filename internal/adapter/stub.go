package adapter

import (
	"context"
	"log"
)

type Adapter interface {
	Collect(ctx context.Context) error
}

type Stub struct{}

func (Stub) Collect(ctx context.Context) error {
	log.Printf("adapter: stub collect (no-op)")
	return nil
}
