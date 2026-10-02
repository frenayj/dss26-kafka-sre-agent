// Package lists downloads and parses the sanctions lists the bank screens
// against, and keeps the latest successful load in memory.
package lists

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync/atomic"
	"time"
)

// Source identifies a list.
type Source string

const (
	OFACSDN       Source = "OFAC_SDN"
	UNConsolidated Source = "UN_CONSOLIDATED"
	EU            Source = "EU"
	UKSanctions   Source = "UK_HMT"
)

// Entry is one designated person or entity, whatever list it came from.
type Entry struct {
	ID      string
	List    Source
	Name    string
	Aliases []string
}

// Feed is where a list is published and how to parse it.
type Feed struct {
	Source Source
	URL    string
	Parse  func(io.Reader) ([]Entry, error)
}

// Feeds are the official publications. URLs are overridable per environment
// (uat points at a mirrored copy).
var Feeds = []Feed{
	{OFACSDN, "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML", parseOFAC},
	{UNConsolidated, "https://scsanctions.un.org/resources/xml/en/consolidated.xml", parseUN},
	{EU, "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content", parseEU},
	{UKSanctions, "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml", parseUK},
}

// Store holds the current entries. Readers never block on a reload.
type Store struct {
	current atomic.Pointer[[]Entry]
	loaded  atomic.Int64
}

func (s *Store) Entries() []Entry {
	if p := s.current.Load(); p != nil {
		return *p
	}
	return nil
}

// LoadedAt is when the last complete load finished.
func (s *Store) LoadedAt() time.Time { return time.Unix(s.loaded.Load(), 0) }

// Refresh loads every feed. If any feed fails the previous set is kept:
// screening against a partial list is worse than screening against a list
// that is 30 minutes old.
func (s *Store) Refresh(ctx context.Context, client *http.Client) error {
	var all []Entry
	for _, f := range Feeds {
		entries, err := fetch(ctx, client, f)
		if err != nil {
			return fmt.Errorf("%s: %w", f.Source, err)
		}
		slog.Info("list loaded", "source", f.Source, "entries", len(entries))
		all = append(all, entries...)
	}
	s.current.Store(&all)
	s.loaded.Store(time.Now().Unix())
	return nil
}

func fetch(ctx context.Context, client *http.Client, f Feed) ([]Entry, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, f.URL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("unexpected status %s", resp.Status)
	}
	return f.Parse(resp.Body)
}

// parseOFAC reads the SDN XML export (sdnList/sdnEntry).
func parseOFAC(r io.Reader) ([]Entry, error) {
	var doc struct {
		Entries []struct {
			UID       string `xml:"uid"`
			FirstName string `xml:"firstName"`
			LastName  string `xml:"lastName"`
			AKAs      []struct {
				FirstName string `xml:"firstName"`
				LastName  string `xml:"lastName"`
			} `xml:"akaList>aka"`
		} `xml:"sdnEntry"`
	}
	if err := xml.NewDecoder(r).Decode(&doc); err != nil {
		return nil, err
	}
	out := make([]Entry, 0, len(doc.Entries))
	for _, e := range doc.Entries {
		entry := Entry{ID: "OFAC-" + e.UID, List: OFACSDN, Name: join(e.FirstName, e.LastName)}
		for _, a := range e.AKAs {
			entry.Aliases = append(entry.Aliases, join(a.FirstName, a.LastName))
		}
		out = append(out, entry)
	}
	return out, nil
}

func join(first, last string) string {
	if first == "" {
		return last
	}
	return first + " " + last
}
