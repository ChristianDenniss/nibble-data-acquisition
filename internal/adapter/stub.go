package adapter

import "context"

type Adapter interface {
	Collect(ctx context.Context) error
}

type Stub struct{}

func (Stub) Collect(ctx context.Context) error {
	return nil
}
