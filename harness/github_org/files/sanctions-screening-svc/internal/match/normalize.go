// Package match scores customer names against sanctions list entries.
package match

import (
	"strings"
	"unicode"

	"golang.org/x/text/runes"
	"golang.org/x/text/transform"
	"golang.org/x/text/unicode/norm"
)

// honorifics and legal-form words carry no identity and only add noise.
var noise = map[string]bool{
	"mr": true, "mrs": true, "ms": true, "dr": true, "sir": true,
	"ltd": true, "llc": true, "plc": true, "gmbh": true, "sa": true, "ooo": true, "jsc": true,
}

// Normalize folds case, strips diacritics and punctuation, drops honorifics
// and legal forms, and sorts nothing: token order matters for Jaro-Winkler,
// so callers compare token sets separately.
func Normalize(name string) string {
	t := transform.Chain(norm.NFD, runes.Remove(runes.In(unicode.Mn)), norm.NFC)
	folded, _, err := transform.String(t, name)
	if err != nil {
		folded = name
	}
	folded = strings.ToLower(folded)
	var b strings.Builder
	for _, r := range folded {
		switch {
		case unicode.IsLetter(r) || unicode.IsDigit(r):
			b.WriteRune(r)
		default:
			b.WriteRune(' ')
		}
	}
	tokens := make([]string, 0, 4)
	for _, tok := range strings.Fields(b.String()) {
		if !noise[tok] {
			tokens = append(tokens, tok)
		}
	}
	return strings.Join(tokens, " ")
}
