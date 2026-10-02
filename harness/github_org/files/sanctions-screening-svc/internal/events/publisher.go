// Package events publishes screening outcomes and listens for profile changes.
package events

import (
	"context"
	_ "embed"
	"fmt"
	"time"

	"github.com/hamba/avro/v2"
	"github.com/twmb/franz-go/pkg/kgo"
	"github.com/twmb/franz-go/pkg/sr"

	"github.com/dss26-org/sanctions-screening-svc/internal/api"
)

const CompletedTopic = "sanctions.screening.completed.v1"

//go:embed schemas/sanctions.screening.completed.v1.avsc
var completedSchema string

type completed struct {
	ScreeningID  string    `avro:"screening_id"`
	CustomerID   string    `avro:"customer_id"`
	Trigger      string    `avro:"trigger"`
	ListsChecked []string  `avro:"lists_checked"`
	Outcome      string    `avro:"outcome"`
	MatchScore   float64   `avro:"match_score"`
	CompletedAt  time.Time `avro:"completed_at"`
}

// Publisher writes sanctions.screening.completed.v1 records keyed by customer.
type Publisher struct {
	client *kgo.Client
	serde  sr.Serde
}

// NewPublisher looks up the registered schema id (the subject is registered by
// CI, never by the service) and prepares the serde.
func NewPublisher(ctx context.Context, client *kgo.Client, registry *sr.Client) (*Publisher, error) {
	subject, err := registry.SchemaByVersion(ctx, CompletedTopic+"-value", -1)
	if err != nil {
		return nil, fmt.Errorf("looking up %s-value: %w", CompletedTopic, err)
	}
	schema, err := avro.Parse(completedSchema)
	if err != nil {
		return nil, err
	}
	var serde sr.Serde
	serde.Register(subject.ID, completed{},
		sr.EncodeFn(func(v any) ([]byte, error) { return avro.Marshal(schema, v) }),
		sr.DecodeFn(func(b []byte, v any) error { return avro.Unmarshal(schema, b, v) }),
	)
	return &Publisher{client: client, serde: serde}, nil
}

// Record implements api.Recorder.
func (p *Publisher) Record(r api.Request, resp api.Response, lists []string, at time.Time) error {
	value, err := p.serde.Encode(completed{
		ScreeningID:  resp.ScreeningID,
		CustomerID:   r.CustomerID,
		Trigger:      r.Trigger,
		ListsChecked: lists,
		Outcome:      resp.Outcome,
		MatchScore:   resp.MatchScore,
		CompletedAt:  at,
	})
	if err != nil {
		return err
	}
	p.client.Produce(context.Background(), &kgo.Record{Topic: CompletedTopic, Key: []byte(r.CustomerID), Value: value}, nil)
	return nil
}
