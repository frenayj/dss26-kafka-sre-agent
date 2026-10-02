package events

import (
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"slices"

	"github.com/hamba/avro/v2"
	"github.com/twmb/franz-go/pkg/kgo"
	"github.com/twmb/franz-go/pkg/sr"
)

const ProfileUpdatedTopic = "customer.profile.updated.v1"

// Fields whose change means the customer must be screened again.
var screeningFields = []string{"first_name", "last_name", "date_of_birth", "nationality", "address"}

type profileUpdated struct {
	CustomerID    string   `avro:"customer_id"`
	ChangedFields []string `avro:"changed_fields"`
}

//go:embed schemas/customer.profile.updated.v1.avsc
var profileSchema string

// ProfileSerde decodes customer.profile.updated.v1 by the schema id on each record.
func ProfileSerde(ctx context.Context, registry *sr.Client) *sr.Serde {
	schema := avro.MustParse(profileSchema)
	var serde sr.Serde
	if subject, err := registry.SchemaByVersion(ctx, ProfileUpdatedTopic+"-value", -1); err == nil {
		serde.Register(subject.ID, profileUpdated{},
			sr.DecodeFn(func(b []byte, v any) error { return avro.Unmarshal(schema, b, v) }))
	}
	return &serde
}

// Rescreen consumes customer.profile.updated.v1 (group sanctions-screening-svc)
// and rescreens customers whose identifying data changed.
type Rescreen struct {
	Client     *kgo.Client
	Serde      *sr.Serde
	ProfileURL string
	Screen     func(ctx context.Context, customerID, name string) error
}

func (r *Rescreen) Run(ctx context.Context) error {
	for {
		fetches := r.Client.PollFetches(ctx)
		if fetches.IsClientClosed() || ctx.Err() != nil {
			return ctx.Err()
		}
		fetches.EachError(func(t string, p int32, err error) {
			slog.Error("fetch error", "topic", t, "partition", p, "err", err)
		})
		var failed error
		fetches.EachRecord(func(rec *kgo.Record) {
			if failed != nil {
				return
			}
			var ev profileUpdated
			if err := r.Serde.Decode(rec.Value, &ev); err != nil {
				failed = fmt.Errorf("decode %s/%d@%d: %w", rec.Topic, rec.Partition, rec.Offset, err)
				return
			}
			if !slices.ContainsFunc(ev.ChangedFields, func(f string) bool { return slices.Contains(screeningFields, f) }) {
				return
			}
			name, err := r.fullName(ctx, ev.CustomerID)
			if err == nil {
				err = r.Screen(ctx, ev.CustomerID, name)
			}
			if err != nil {
				failed = err
			}
		})
		if failed != nil {
			// Do not commit: the batch is retried after a pause.
			return failed
		}
		if err := r.Client.CommitUncommittedOffsets(ctx); err != nil {
			slog.Error("commit failed", "err", err)
		}
	}
}

func (r *Rescreen) fullName(ctx context.Context, customerID string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, r.ProfileURL+"/v1/customers/"+customerID, nil)
	if err != nil {
		return "", err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	var body struct {
		FirstName string `json:"firstName"`
		LastName  string `json:"lastName"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return "", err
	}
	return body.FirstName + " " + body.LastName, nil
}
