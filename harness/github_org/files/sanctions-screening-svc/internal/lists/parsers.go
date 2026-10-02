package lists

import (
	"encoding/xml"
	"io"
	"strings"
)

// parseUN reads the UN Security Council consolidated list.
func parseUN(r io.Reader) ([]Entry, error) {
	var doc struct {
		Individuals []struct {
			Ref     string `xml:"REFERENCE_NUMBER"`
			First   string `xml:"FIRST_NAME"`
			Second  string `xml:"SECOND_NAME"`
			Third   string `xml:"THIRD_NAME"`
			Aliases []struct {
				Name string `xml:"ALIAS_NAME"`
			} `xml:"INDIVIDUAL_ALIAS"`
		} `xml:"INDIVIDUALS>INDIVIDUAL"`
		Entities []struct {
			Ref  string `xml:"REFERENCE_NUMBER"`
			Name string `xml:"FIRST_NAME"`
		} `xml:"ENTITIES>ENTITY"`
	}
	if err := xml.NewDecoder(r).Decode(&doc); err != nil {
		return nil, err
	}
	var out []Entry
	for _, i := range doc.Individuals {
		e := Entry{ID: "UN-" + i.Ref, List: UNConsolidated, Name: strings.Join(nonEmpty(i.First, i.Second, i.Third), " ")}
		for _, a := range i.Aliases {
			if a.Name != "" {
				e.Aliases = append(e.Aliases, a.Name)
			}
		}
		out = append(out, e)
	}
	for _, en := range doc.Entities {
		out = append(out, Entry{ID: "UN-" + en.Ref, List: UNConsolidated, Name: en.Name})
	}
	return out, nil
}

// parseEU reads the EU Financial Sanctions Files (FSF) full list.
func parseEU(r io.Reader) ([]Entry, error) {
	var doc struct {
		Entities []struct {
			LogicalID string `xml:"logicalId,attr"`
			Names     []struct {
				Whole string `xml:"wholeName,attr"`
			} `xml:"nameAlias"`
		} `xml:"sanctionEntity"`
	}
	if err := xml.NewDecoder(r).Decode(&doc); err != nil {
		return nil, err
	}
	out := make([]Entry, 0, len(doc.Entities))
	for _, s := range doc.Entities {
		if len(s.Names) == 0 {
			continue
		}
		e := Entry{ID: "EU-" + s.LogicalID, List: EU, Name: s.Names[0].Whole}
		for _, n := range s.Names[1:] {
			e.Aliases = append(e.Aliases, n.Whole)
		}
		out = append(out, e)
	}
	return out, nil
}

// parseUK reads the FCDO UK Sanctions List (the only UK source since OFSI
// closed its consolidated list on 28 January 2026).
func parseUK(r io.Reader) ([]Entry, error) {
	var doc struct {
		Designations []struct {
			UniqueID string `xml:"UniqueID"`
			Names    []struct {
				Name string `xml:"Name6"`
				Type string `xml:"NameType"`
			} `xml:"Names>Name"`
		} `xml:"Designation"`
	}
	if err := xml.NewDecoder(r).Decode(&doc); err != nil {
		return nil, err
	}
	var out []Entry
	for _, d := range doc.Designations {
		e := Entry{ID: "UK-" + d.UniqueID, List: UKSanctions}
		for _, n := range d.Names {
			if n.Type == "Primary Name" && e.Name == "" {
				e.Name = n.Name
			} else if n.Name != "" {
				e.Aliases = append(e.Aliases, n.Name)
			}
		}
		out = append(out, e)
	}
	return out, nil
}

func nonEmpty(parts ...string) []string {
	out := parts[:0]
	for _, p := range parts {
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
