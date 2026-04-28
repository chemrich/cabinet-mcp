"""
Stress tests for the furniture_refs module.

Covers:
- All 81 canonical piece names are findable by exact lookup
- Key synonyms resolve to the right canonical piece
- SYNONYM_TO_PRESETS consistency: every referenced preset slug exists
- Fuzzy / partial matching returns candidates
- Edge cases: empty query, whitespace, symbols, accented characters
- Index integrity: no canonical piece maps to a different piece's ref
"""

import pytest

from cadquery_furniture.furniture_refs import (
    FURNITURE_REFS,
    SYNONYM_TO_PRESETS,
    FurnitureRef,
    get_furniture,
    identify_furniture,
    _norm,
)
from cadquery_furniture.presets import PRESETS


# ─── Canonical piece lookup ────────────────────────────────────────────────────

class TestCanonicalLookup:
    """Every canonical piece name must be findable by get_furniture."""

    @pytest.mark.parametrize("ref", FURNITURE_REFS, ids=lambda r: r.piece)
    def test_canonical_name_is_findable(self, ref: FurnitureRef):
        found = get_furniture(ref.piece)
        assert found is not None, f"get_furniture({ref.piece!r}) returned None"
        assert found.piece == ref.piece, (
            f"Expected canonical piece {ref.piece!r}, got {found.piece!r}"
        )

    @pytest.mark.parametrize("ref", FURNITURE_REFS, ids=lambda r: r.piece)
    def test_identify_returns_canonical_as_first(self, ref: FurnitureRef):
        results = identify_furniture(ref.piece)
        assert results, f"identify_furniture({ref.piece!r}) returned empty list"
        assert results[0].piece == ref.piece, (
            f"First result for {ref.piece!r} was {results[0].piece!r}, expected exact match first"
        )


# ─── Synonym resolution ────────────────────────────────────────────────────────

class TestSynonymResolution:
    """Synonyms should resolve to their owning canonical piece (not a different one)."""

    # Critical synonym pairs: (synonym, expected canonical piece)
    CASES = [
        ("buffet",          "Buffet"),           # canonical, not Sideboard's synonym
        ("credenza",        "Credenza"),          # canonical, not Media console's synonym
        ("wardrobe",        "Wardrobe"),          # canonical, not cross-ref via Armoire
        ("armoire",         "Armoire"),
        ("tallboy",         "Tallboy"),
        ("highboy",         "Highboy"),
        ("chiffonier",      "Chiffonier"),
        ("semainier",       "Semainier"),
        ("lingerie chest",  "Lingerie chest"),
        ("nightstand",      "Nightstand"),
        ("chevet",          "Chevet"),
        ("bedside cabinet", "Bedside cabinet"),
        ("dresser",         "Dresser"),
        ("commode",         "Commode"),
        ("chest of drawers","Chest of drawers"),
        ("linen tower",     "Linen tower"),
        ("linen cabinet",   "Linen cabinet"),
        ("filing cabinet",  "Filing cabinet"),
        ("hall tree",       "Hall tree"),
        ("entry cabinet",   "Entry cabinet"),
        ("bar cabinet",     "Bar cabinet"),
        ("media console",   "Media console"),
        ("tool chest",      "Tool chest"),
        ("schrank",         "Schrank"),
        ("armadio",         "Armadio"),
    ]

    @pytest.mark.parametrize("query,expected_piece", CASES)
    def test_synonym_resolves_to_correct_piece(self, query, expected_piece):
        found = get_furniture(query)
        assert found is not None, f"get_furniture({query!r}) returned None"
        assert found.piece == expected_piece, (
            f"Query {query!r}: expected {expected_piece!r}, got {found.piece!r}"
        )

    def test_cross_reference_synonym_does_not_steal_canonical(self):
        # "Credenza" is a synonym of Sideboard AND Media console — it must resolve
        # to its own canonical entry, not a neighbour's cross-reference.
        found = get_furniture("credenza")
        assert found.piece == "Credenza"

    def test_dresser_not_overwritten_by_chest_of_drawers(self):
        # "Dresser" is also listed as a synonym of "Chest of drawers" —
        # the canonical "Dresser" entry must win.
        found = get_furniture("dresser")
        assert found.piece == "Dresser"
        assert "bedroom_dresser" in found.preset_keys

    def test_credenza_preset_keys_are_credenza_not_sideboard(self):
        found = get_furniture("credenza")
        assert "living_room_credenza" in found.preset_keys
        assert "living_room_sideboard" not in found.preset_keys


# ─── SYNONYM_TO_PRESETS consistency ───────────────────────────────────────────

class TestSynonymToPresetsConsistency:
    """Every preset slug referenced in SYNONYM_TO_PRESETS must exist in PRESETS."""

    def test_all_referenced_preset_slugs_exist(self):
        missing = []
        for norm_name, slugs in SYNONYM_TO_PRESETS.items():
            for slug in slugs:
                if slug not in PRESETS:
                    missing.append((norm_name, slug))
        assert not missing, (
            f"SYNONYM_TO_PRESETS references {len(missing)} unknown preset(s): {missing[:5]}"
        )

    def test_all_furniture_ref_preset_keys_exist(self):
        missing = []
        for ref in FURNITURE_REFS:
            for slug in ref.preset_keys:
                if slug not in PRESETS:
                    missing.append((ref.piece, slug))
        assert not missing, (
            f"{len(missing)} FurnitureRef preset_keys are missing: {missing}"
        )

    def test_armoire_maps_to_both_presets(self):
        slugs = SYNONYM_TO_PRESETS.get(_norm("armoire"), ())
        assert "bedroom_armoire" in slugs
        assert "armoire_2col" in slugs

    def test_armoire_simple_preset_is_first(self):
        # bedroom_armoire (simpler) should be suggested before armoire_2col (advanced).
        slugs = SYNONYM_TO_PRESETS.get(_norm("armoire"), ())
        assert slugs[0] == "bedroom_armoire"

    def test_chiffonier_maps_to_chiffoniere_first(self):
        slugs = SYNONYM_TO_PRESETS.get(_norm("chiffonier"), ())
        assert slugs[0] == "bedroom_chiffoniere"

    def test_wardrobe_maps_to_bedroom_armoire_first(self):
        slugs = SYNONYM_TO_PRESETS.get(_norm("wardrobe"), ())
        assert slugs[0] == "bedroom_armoire"


# ─── Partial / fuzzy matching ─────────────────────────────────────────────────

class TestFuzzyMatching:

    def test_prefix_chest_returns_multiple(self):
        results = identify_furniture("chest")
        assert len(results) >= 2, "Expected multiple matches for 'chest'"
        pieces = [r.piece for r in results]
        # Should find "Chest of drawers", "Chest-on-chest", "Tool chest" etc.
        assert any("chest" in p.lower() for p in pieces)

    def test_prefix_cabinet_returns_multiple(self):
        results = identify_furniture("cabinet")
        assert len(results) >= 3

    def test_partial_console_matches(self):
        results = identify_furniture("console")
        pieces = [r.piece for r in results]
        assert any("console" in p.lower() or "Console" in p for p in pieces)

    def test_max_five_candidates(self):
        # identify_furniture caps results at 5
        results = identify_furniture("a")
        assert len(results) <= 5

    def test_full_foreign_word_armadio(self):
        results = identify_furniture("armadio")
        assert results and results[0].piece == "Armadio"

    def test_full_foreign_word_schrank(self):
        results = identify_furniture("schrank")
        assert results and results[0].piece == "Schrank"

    def test_french_term_secrétaire(self):
        # Canonical name has an accent
        found = get_furniture("Secrétaire à abattant")
        assert found is not None
        assert found.piece == "Secrétaire à abattant"


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_string_returns_empty_list(self):
        assert identify_furniture("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert identify_furniture("   ") == []

    def test_get_furniture_empty_returns_none(self):
        assert get_furniture("") is None

    def test_gibberish_returns_empty(self):
        assert identify_furniture("xyzzy_widget_matic_9000") == []

    def test_get_furniture_gibberish_returns_none(self):
        assert get_furniture("not-a-real-piece") is None

    def test_case_insensitive_upper(self):
        assert get_furniture("SIDEBOARD") is not None
        assert get_furniture("SIDEBOARD").piece == "Sideboard"

    def test_case_insensitive_mixed(self):
        assert get_furniture("ChEsT oF dRaWeRs") is not None

    def test_trailing_whitespace_ignored(self):
        assert get_furniture("  dresser  ") is not None

    def test_piece_with_apostrophe(self):
        # "Gentleman's chest" has a curly apostrophe in description; ASCII ' should work
        found = get_furniture("Gentleman's chest")
        assert found is not None
        assert found.piece == "Gentleman's chest"

    def test_all_categories_represented(self):
        categories = {ref.category for ref in FURNITURE_REFS}
        expected = {
            "Case Pieces & Storage",
            "Wardrobes & Armoires",
            "Bedroom",
            "Kitchen & Dining",
            "Entryway & Living Room",
            "Bathroom",
            "Office & Desk",
            "Workshop & Utility",
            "Antique & Regional",
        }
        assert expected == categories

    def test_total_ref_count(self):
        assert len(FURNITURE_REFS) == 80

    def test_no_duplicate_canonical_pieces(self):
        pieces = [ref.piece for ref in FURNITURE_REFS]
        dupes = [p for p in pieces if pieces.count(p) > 1]
        assert not dupes, f"Duplicate canonical pieces: {dupes}"
