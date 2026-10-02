// Package api serves synchronous screening for onboarding and payments.
package api

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"github.com/dss26-org/sanctions-screening-svc/internal/match"
)

// Trigger values mirror the SanctionsTrigger enum on sanctions.screening.completed.v1.
var triggers = map[string]bool{
	"ACCOUNT_OPEN": true, "PERIODIC_REFRESH": true, "CROSS_BORDER_TXN": true, "BENEFICIARY_ADDED": true,
}

type Request struct {
	CustomerID string `json:"customerId"`
	Name       string `json:"name"`
	Trigger    string `json:"trigger"`
}

type Response struct {
	ScreeningID string      `json:"screeningId"`
	Outcome     string      `json:"outcome"` // NO_HIT or POTENTIAL_MATCH; analysts confirm or clear later
	MatchScore  float64     `json:"matchScore"`
	Hits        []match.Hit `json:"hits,omitempty"`
}

// Recorder publishes the outcome; implemented by events.Publisher.
type Recorder interface {
	Record(r Request, resp Response, lists []string, at time.Time) error
}

type Handler struct {
	Matcher  func() *match.Matcher
	Lists    []string
	Recorder Recorder
	NewID    func() string
}

func (h *Handler) Routes() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/screenings", h.screen)
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	return mux
}

func (h *Handler) screen(w http.ResponseWriter, r *http.Request) {
	var req Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.Name == "" || !triggers[req.Trigger] {
		http.Error(w, `{"error":"customerId, name and a valid trigger are required"}`, http.StatusBadRequest)
		return
	}
	hits := h.Matcher().Screen(req.Name)
	resp := Response{ScreeningID: h.NewID(), Outcome: "NO_HIT", Hits: hits}
	if len(hits) > 0 {
		resp.Outcome = "POTENTIAL_MATCH"
		resp.MatchScore = hits[0].Score
	}
	if err := h.Recorder.Record(req, resp, h.Lists, time.Now()); err != nil {
		// The caller gets the answer either way; the event is retried by the
		// producer, and a failure here must never let a payment through unscreened.
		slog.Error("recording screening failed", "screening_id", resp.ScreeningID, "err", err)
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}
