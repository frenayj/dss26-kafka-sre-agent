package match

import (
	"testing"

	"github.com/dss26-org/sanctions-screening-svc/internal/lists"
)

func TestNormalizeFoldsDiacriticsAndHonorifics(t *testing.T) {
	cases := map[string]string{
		"Mr. José  Álvarez-Núñez": "jose alvarez nunez",
		"ACME TRADING LLC":        "acme trading",
		"  Dr Zoë O'Brien ":       "zoe o brien",
	}
	for in, want := range cases {
		if got := Normalize(in); got != want {
			t.Errorf("Normalize(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestJaroWinklerKnownValues(t *testing.T) {
	if got := JaroWinkler("martha", "marhta"); got < 0.96 || got > 0.962 {
		t.Errorf("martha/marhta = %.4f, want ~0.961", got)
	}
	if got := JaroWinkler("abc", "xyz"); got != 0 {
		t.Errorf("abc/xyz = %.4f, want 0", got)
	}
}

func TestScreenFindsAliasWithTypo(t *testing.T) {
	m := NewMatcher([]lists.Entry{
		{ID: "EU-2022-0147", List: lists.EU, Name: "Ivan Petrovich Sidorov", Aliases: []string{"Ivan Sidorov"}},
		{ID: "OFAC-41022", List: lists.OFACSDN, Name: "Northern Star Shipping LLC"},
	}, 0.88)

	hits := m.Screen("Ivan Sidorow")
	if len(hits) != 1 || hits[0].Entry.ID != "EU-2022-0147" {
		t.Fatalf("hits = %+v, want EU-2022-0147", hits)
	}
	if got := m.Screen("Jane Smith"); len(got) != 0 {
		t.Fatalf("unexpected hits for an unrelated name: %+v", got)
	}
}
