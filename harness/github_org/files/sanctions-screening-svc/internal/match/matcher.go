package match

import (
	"sort"

	"github.com/dss26-org/sanctions-screening-svc/internal/lists"
)

// Hit is one list entry that scored at or above the review threshold.
type Hit struct {
	Entry lists.Entry
	Score float64
}

// Matcher compares names against every loaded list. It is safe for
// concurrent use once built; reloads swap in a new Matcher.
type Matcher struct {
	threshold float64
	entries   []indexed
}

type indexed struct {
	entry lists.Entry
	names []string // normalised primary name and aliases
}

// NewMatcher indexes entries. threshold is the score at which a hit goes to
// an analyst (0.88 since the 2021 calibration against the OFAC test set).
func NewMatcher(entries []lists.Entry, threshold float64) *Matcher {
	m := &Matcher{threshold: threshold, entries: make([]indexed, 0, len(entries))}
	for _, e := range entries {
		ix := indexed{entry: e}
		for _, n := range append([]string{e.Name}, e.Aliases...) {
			if nn := Normalize(n); nn != "" {
				ix.names = append(ix.names, nn)
			}
		}
		m.entries = append(m.entries, ix)
	}
	return m
}

// Screen returns every hit for name, best first.
func (m *Matcher) Screen(name string) []Hit {
	q := Normalize(name)
	if q == "" {
		return nil
	}
	var hits []Hit
	for _, ix := range m.entries {
		best := 0.0
		for _, n := range ix.names {
			if s := JaroWinkler(q, n); s > best {
				best = s
			}
		}
		if best >= m.threshold {
			hits = append(hits, Hit{Entry: ix.entry, Score: best})
		}
	}
	sort.Slice(hits, func(i, j int) bool { return hits[i].Score > hits[j].Score })
	return hits
}
