package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/twmb/franz-go/pkg/kgo"
	"github.com/twmb/franz-go/pkg/sasl/scram"
	"github.com/twmb/franz-go/pkg/sr"

	"github.com/dss26-org/sanctions-screening-svc/internal/api"
	"github.com/dss26-org/sanctions-screening-svc/internal/events"
	"github.com/dss26-org/sanctions-screening-svc/internal/lists"
	"github.com/dss26-org/sanctions-screening-svc/internal/match"
)

const refreshEvery = 30 * time.Minute

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	store := &lists.Store{}
	httpClient := &http.Client{Timeout: 2 * time.Minute}
	if err := store.Refresh(ctx, httpClient); err != nil {
		slog.Error("initial list load failed - refusing to start", "err", err)
		os.Exit(1)
	}
	var matcher atomic.Pointer[match.Matcher]
	matcher.Store(match.NewMatcher(store.Entries(), 0.88))
	go func() {
		for range time.Tick(refreshEvery) {
			if err := store.Refresh(ctx, httpClient); err != nil {
				slog.Error("list refresh failed, keeping previous lists", "err", err, "loaded_at", store.LoadedAt())
				continue
			}
			matcher.Store(match.NewMatcher(store.Entries(), 0.88))
		}
	}()

	brokers := strings.Split(os.Getenv("KAFKA_BOOTSTRAP_SERVERS"), ",")
	auth := scram.Auth{User: os.Getenv("KAFKA_USERNAME"), Pass: os.Getenv("KAFKA_PASSWORD")}
	producer, err := kgo.NewClient(
		kgo.SeedBrokers(brokers...),
		kgo.SASL(auth.AsSha512Mechanism()),
		kgo.RequiredAcks(kgo.AllISRAcks()),
		kgo.ClientID("sanctions-screening-svc"),
	)
	if err != nil {
		slog.Error("kafka client", "err", err)
		os.Exit(1)
	}
	defer producer.Close()

	registry, err := sr.NewClient(sr.URLs(os.Getenv("SCHEMA_REGISTRY_URL")))
	if err != nil {
		slog.Error("schema registry client", "err", err)
		os.Exit(1)
	}
	publisher, err := events.NewPublisher(ctx, producer, registry)
	if err != nil {
		slog.Error("publisher", "err", err)
		os.Exit(1)
	}

	h := &api.Handler{
		Matcher:  matcher.Load,
		Lists:    []string{string(lists.OFACSDN), string(lists.UNConsolidated), string(lists.EU), string(lists.UKSanctions)},
		Recorder: publisher,
		NewID:    newID,
	}

	consumer, err := kgo.NewClient(
		kgo.SeedBrokers(brokers...),
		kgo.SASL(auth.AsSha512Mechanism()),
		kgo.ConsumerGroup("sanctions-screening-svc"),
		kgo.ConsumeTopics(events.ProfileUpdatedTopic),
		kgo.DisableAutoCommit(),
		kgo.ClientID("sanctions-screening-svc"),
	)
	if err != nil {
		slog.Error("kafka consumer", "err", err)
		os.Exit(1)
	}
	defer consumer.Close()
	rescreen := &events.Rescreen{
		Client:     consumer,
		Serde:      events.ProfileSerde(ctx, registry),
		ProfileURL: os.Getenv("CUSTOMER_PROFILE_URL"),
		Screen: func(_ context.Context, customerID, name string) error {
			hits := matcher.Load().Screen(name)
			resp := api.Response{ScreeningID: newID(), Outcome: "NO_HIT", Hits: hits}
			if len(hits) > 0 {
				resp.Outcome, resp.MatchScore = "POTENTIAL_MATCH", hits[0].Score
			}
			req := api.Request{CustomerID: customerID, Name: name, Trigger: "PERIODIC_REFRESH"}
			return publisher.Record(req, resp, h.Lists, time.Now())
		},
	}
	go func() {
		for ctx.Err() == nil {
			if err := rescreen.Run(ctx); err != nil && ctx.Err() == nil {
				slog.Error("rescreen loop stopped, restarting in 30s", "err", err)
				time.Sleep(30 * time.Second)
			}
		}
	}()

	srv := &http.Server{Addr: ":8080", Handler: h.Routes(), ReadHeaderTimeout: 5 * time.Second}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdown)
	}()
	slog.Info("listening", "addr", srv.Addr, "entries", len(store.Entries()))
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		slog.Error("server", "err", err)
		os.Exit(1)
	}
}

func newID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
