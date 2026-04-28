"""
Furniture reference data derived from docs/furniture_refs.csv.

Provides a catalogue of 81 named furniture pieces with their canonical names,
synonyms, typical dimensions, and mappings to cabinet presets.  The primary
use-cases are:

- ``identify_furniture(query)`` — look up a piece by any name or synonym
- ``SYNONYM_TO_PRESETS``        — flat dict: normalised name → tuple of preset slugs
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Helper ────────────────────────────────────────────────────────────────────

def _mm(inches: float) -> int:
    return round(inches * 25.4)


def _parse_example(s: str) -> tuple[int, int, int]:
    """Parse 'H × W × D″' in inches → (h_mm, w_mm, d_mm)."""
    parts = [p.strip().rstrip('″"\'') for p in s.split("×")]
    h, w, d = (float(p) for p in parts)
    return _mm(h), _mm(w), _mm(d)


def _syns(raw: str) -> tuple[str, ...]:
    """Strip the '*' cross-reference marker and return a clean synonym tuple."""
    if raw in ("—", "", "-"):
        return ()
    return tuple(s.strip().rstrip("*") for s in raw.split(",") if s.strip() not in ("—", ""))


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FurnitureRef:
    category: str
    piece: str
    synonyms: tuple[str, ...]
    typical_dims: str        # imperial range string, e.g. "60–72″W × 18–20″D × 34–36″H"
    example_h_mm: int        # from example column (H × W × D in inches)
    example_w_mm: int
    example_d_mm: int
    description: str
    preset_keys: tuple[str, ...]  # matching preset slugs (may be empty)

    def all_names(self) -> tuple[str, ...]:
        """Canonical name + all synonyms as one tuple (for index building)."""
        return (self.piece,) + self.synonyms

    def to_dict(self) -> dict:
        return {
            "piece": self.piece,
            "category": self.category,
            "description": self.description,
            "typical_dims": self.typical_dims,
            "example_dims_mm": {
                "h": self.example_h_mm,
                "w": self.example_w_mm,
                "d": self.example_d_mm,
            },
            "synonyms": list(self.synonyms),
            "preset_keys": list(self.preset_keys),
        }


# ── Catalogue ─────────────────────────────────────────────────────────────────
# (category, piece, synonyms_raw, typical_dims, example_hwdin, description, preset_slugs)

_RAW: list[tuple] = [
    # ── Case Pieces & Storage ──────────────────────────────────────────────────
    (
        "Case Pieces & Storage", "Sideboard", "Buffet*, Credenza*",
        "60–72″W × 18–20″D × 34–36″H", "35 × 66 × 19″",
        "Long low case piece with drawers and cabinet doors; used in dining rooms for linens and serving ware.",
        ("living_room_sideboard",),
    ),
    (
        "Case Pieces & Storage", "Buffet", "Sideboard*, Credenza*",
        "60–72″W × 18–20″D × 34–36″H", "35 × 66 × 19″",
        "Effectively synonymous with sideboard in modern use. Historically a tiered serving piece.",
        ("living_room_sideboard",),
    ),
    (
        "Case Pieces & Storage", "Credenza", "Sideboard*, Buffet*",
        "60–72″W × 18″D × 30″H", "30 × 66 × 18″",
        "Originally an Italian Renaissance side table. Today nearly synonymous with sideboard; often lower and associated with office/media use.",
        ("living_room_credenza",),
    ),
    (
        "Case Pieces & Storage", "Hutch", "China hutch, Welsh dresser*",
        "42–60″W × 16″D × 72–84″H", "78 × 54 × 16″",
        "Two-part piece: lower cabinet with drawers and doors topped by an open or glazed upper cabinet for display.",
        (),
    ),
    (
        "Case Pieces & Storage", "China cabinet", "China hutch, Display cabinet*",
        "36–54″W × 16″D × 72–84″H", "78 × 48 × 16″",
        "Tall glazed cabinet with lower storage base; designed to display and store china and glassware.",
        (),
    ),
    (
        "Case Pieces & Storage", "Display cabinet", "China cabinet*, Curio cabinet*",
        "30–48″W × 14″D × 70–80″H", "76 × 40 × 14″",
        "Glass-fronted cabinet for displaying collectibles or china. Overlaps with china cabinet and curio cabinet.",
        (),
    ),
    (
        "Case Pieces & Storage", "Curio cabinet", "Display cabinet*, Vitrine*",
        "24–36″W × 14″D × 60–72″H", "68 × 30 × 14″",
        "Glass-sided cabinet for displaying small collectibles. Frequently in corner or pedestal variants.",
        (),
    ),
    (
        "Case Pieces & Storage", "Vitrine", "Curio cabinet*, Display cabinet*",
        "24–36″W × 14″D × 60–72″H", "68 × 30 × 14″",
        "French term for a glass display case; functionally equivalent to a curio cabinet. May be wall-mounted or freestanding.",
        (),
    ),
    (
        "Case Pieces & Storage", "Breakfront", "—",
        "72–96″W × 16″D × 84–96″H", "90 × 84 × 16″",
        "Large case piece whose center section projects forward. Glazed upper doors; solid lower cabinet doors and drawers.",
        (),
    ),
    (
        "Case Pieces & Storage", "Secretary desk", "Escritoire, Bureau*, Secrétaire à abattant*",
        "30–36″W × 18″D × 60–80″H", "72 × 32 × 18″",
        "Desk-and-cabinet combination with fall-front writing surface concealing pigeonholes; glazed upper doors; drawers below.",
        (),
    ),
    (
        "Case Pieces & Storage", "Secrétaire à abattant", "Secretary desk*, Fall-front secretary",
        "30–36″W × 16″D × 56–72″H", "65 × 34 × 16″",
        "French fall-front secretary. Vertical cabinet with drop-down writing leaf revealing interior drawers and pigeonholes.",
        (),
    ),
    (
        "Case Pieces & Storage", "Escritoire", "Secretary desk*, Bureau*",
        "28–36″W × 18″D × 40–50″H", "45 × 32 × 18″",
        "Small writing desk with fitted interior; often with fall front and drawers below. More compact than a full secretary.",
        (),
    ),
    (
        "Case Pieces & Storage", "Bureau", "Secretary desk*, Chest of drawers*",
        "36–48″W × 18″D × 50–72″H", "60 × 42 × 18″",
        "Ambiguous: in the US often means a dresser; in Europe often a writing desk with drawers.",
        ("bedroom_dresser",),
    ),
    (
        "Case Pieces & Storage", "Roll-top desk", "Cylinder desk*",
        "48–60″W × 28″D × 48″H", "48 × 54 × 28″",
        "Writing desk with a tambour cover that rolls up to reveal a fitted interior with small drawers. Pedestal drawers below.",
        (),
    ),
    (
        "Case Pieces & Storage", "Cylinder desk", "Roll-top desk*",
        "48–60″W × 28″D × 48″H", "48 × 54 × 28″",
        "Similar to roll-top but with a quarter-round solid cover that slides back. Fitted interior; pedestal drawers below.",
        (),
    ),
    # ── Wardrobes & Armoires ──────────────────────────────────────────────────
    (
        "Wardrobes & Armoires", "Armoire", "Wardrobe*, Schrank*, Armadio*",
        "40–54″W × 22″D × 72–84″H", "80 × 48 × 22″",
        "Large freestanding cabinet with two doors enclosing hanging space and shelves; often a base drawer. French origin.",
        ("bedroom_armoire", "armoire_2col"),
    ),
    (
        "Wardrobes & Armoires", "Wardrobe", "Armoire*",
        "40–72″W × 22″D × 72–84″H", "80 × 54 × 22″",
        "Freestanding cabinet for clothing with hanging rail and shelves. 'Wardrobe' is the English term; 'armoire' the French equivalent.",
        ("bedroom_armoire", "armoire_2col"),
    ),
    (
        "Wardrobes & Armoires", "Chifforobe", "Chiffonier + wardrobe hybrid",
        "36–48″W × 20″D × 60–72″H", "68 × 42 × 20″",
        "Hybrid combining a wardrobe section with hanging space alongside a column of drawers. Name is a portmanteau of chiffonier and wardrobe.",
        ("bedroom_gentleman_chest",),
    ),
    (
        "Wardrobes & Armoires", "Chiffonier", "Semainier*, Lingerie chest*",
        "20–28″W × 18″D × 48–60″H", "54 × 24 × 18″",
        "Tall narrow chest with many small drawers for handkerchiefs and lace. May include a mirror or small door above.",
        ("bedroom_chiffoniere", "bedroom_lingerie_chest"),
    ),
    (
        "Wardrobes & Armoires", "Tallboy", "Highboy*, Chest-on-chest*",
        "36–44″W × 20″D × 60–72″H", "66 × 40 × 20″",
        "British term for a tall chest of drawers in two sections. Equivalent to highboy in American usage.",
        ("bedroom_tall_chest",),
    ),
    (
        "Wardrobes & Armoires", "Highboy", "Tallboy*, Chest-on-chest*",
        "36–44″W × 22″D × 60–84″H", "72 × 40 × 22″",
        "American term for a tall chest on a stand (lowboy base). Typically two-part with decorative cornice; a formal antique form.",
        ("bedroom_tall_chest",),
    ),
    (
        "Wardrobes & Armoires", "Lowboy", "Dressing table*",
        "30–36″W × 20″D × 28–32″H", "30 × 32 × 20″",
        "The lower stand section of a highboy when used independently; a low table with one or more shallow drawers.",
        (),
    ),
    (
        "Wardrobes & Armoires", "Chest-on-chest", "Tallboy*, Highboy*",
        "36–44″W × 20″D × 60–72″H", "66 × 40 × 20″",
        "Two chests of drawers stacked vertically. Distinct from highboy in that it has no leg stand.",
        ("bedroom_tall_chest",),
    ),
    (
        "Wardrobes & Armoires", "Linen press", "Armoire*",
        "40–54″W × 22″D × 72–80″H", "76 × 48 × 22″",
        "Wardrobe-style cabinet with upper doors concealing shelves for folded linens (not a hanging rail); drawers in lower section.",
        ("bathroom_linen_tower",),
    ),
    (
        "Wardrobes & Armoires", "Kas", "Kast, Schrank*",
        "60–72″W × 26″D × 72–84″H", "80 × 66 × 26″",
        "Massive Dutch-American wardrobe with large paneled doors and heavy cornice. Drawers below main cabinet. 17th–18th c. New York/New Jersey.",
        (),
    ),
    (
        "Wardrobes & Armoires", "Schrank", "Kas*, Armoire*",
        "54–72″W × 24″D × 72–84″H", "80 × 64 × 24″",
        "Germanic large wardrobe cabinet similar in scale to the kas. Often with carved panels; large doors over shelves/hanging space with drawer base.",
        ("bedroom_armoire", "armoire_2col"),
    ),
    (
        "Wardrobes & Armoires", "Bonnetière", "—",
        "22–28″W × 16″D × 72–84″H", "80 × 24 × 16″",
        "Narrow French single-door wardrobe; tall enough to store a bonnet. A slender armoire variant suited to small spaces.",
        (),
    ),
    (
        "Wardrobes & Armoires", "Armadio", "Armoire*",
        "48–72″W × 24″D × 80–90″H", "86 × 60 × 24″",
        "Italian term for a large wardrobe; functionally identical to the armoire, often more architectural in detailing.",
        ("bedroom_armoire", "armoire_2col"),
    ),
    # ── Bedroom ───────────────────────────────────────────────────────────────
    (
        "Bedroom", "Dresser", "Bureau*, Double dresser*",
        "50–66″W × 18″D × 30–36″H", "33 × 58 × 18″",
        "Wide low chest of drawers for bedroom use; typically 3–4 rows. Often paired with a mirror mounted above.",
        ("bedroom_dresser",),
    ),
    (
        "Bedroom", "Double dresser", "Dresser*",
        "58–68″W × 18″D × 30–36″H", "33 × 64 × 18″",
        "Wider dresser with drawers in two columns. The most common dresser format today.",
        ("bedroom_dresser",),
    ),
    (
        "Bedroom", "Triple dresser", "Dresser*",
        "72–84″W × 18″D × 30–36″H", "33 × 78 × 18″",
        "Extra-wide dresser with drawers in three columns; provides maximum horizontal bedroom storage.",
        ("bedroom_dresser",),
    ),
    (
        "Bedroom", "Bachelor's chest", "—",
        "30–36″W × 18″D × 30–36″H", "33 × 32 × 18″",
        "Compact chest of drawers; typically 3–4 drawers wide and 2–3 drawers tall. Scaled for small spaces.",
        ("bedroom_tall_chest",),
    ),
    (
        "Bedroom", "Lingerie chest", "Semainier*, Chiffonier*",
        "18–24″W × 18″D × 48–60″H", "54 × 20 × 18″",
        "Tall narrow chest with many shallow drawers for folded delicates. Narrower than a standard chest of drawers.",
        ("bedroom_lingerie_chest",),
    ),
    (
        "Bedroom", "Gentleman's chest", "—",
        "48–60″W × 18″D × 48–60″H", "54 × 54 × 18″",
        "Combination chest with a wardrobe section with hanging rod behind doors on one side and a column of drawers on the other.",
        ("bedroom_gentleman_chest",),
    ),
    (
        "Bedroom", "Semainier", "Lingerie chest*, Chiffonier*",
        "16–22″W × 16″D × 48–60″H", "54 × 18 × 16″",
        "French chest with exactly seven drawers (one per day of the week). Tall and narrow; for folded garments.",
        ("bedroom_lingerie_chest",),
    ),
    (
        "Bedroom", "Nightstand", "Bedside table, Bedside cabinet*, Chevet*",
        "18–24″W × 16″D × 24–30″H", "26 × 22 × 16″",
        "Small table placed beside a bed with one or two drawers and sometimes a lower shelf or cabinet door.",
        ("bedroom_nightstand",),
    ),
    (
        "Bedroom", "Bedside cabinet", "Nightstand*, Chevet*",
        "16–24″W × 14″D × 24–30″H", "26 × 20 × 16″",
        "Small cabinet for bedside use; often with a door rather than a drawer. Functionally equivalent to a nightstand.",
        ("bedroom_nightstand",),
    ),
    (
        "Bedroom", "Chevet", "Nightstand*, Bedside cabinet*",
        "16–22″W × 14″D × 24–28″H", "26 × 18 × 14″",
        "French term for a bedside table. May have a drawer or cabinet door. Synonym of nightstand in modern use.",
        ("bedroom_nightstand",),
    ),
    (
        "Bedroom", "Commode", "Chest of drawers*",
        "28–36″W × 18″D × 32–38″H", "35 × 32 × 18″",
        "In antique/French furniture: a low wide chest of drawers; often ornately decorated with curved fronts and gilt hardware.",
        ("bedroom_dresser",),
    ),
    (
        "Bedroom", "Chest of drawers", "Dresser*, Bureau*",
        "30–48″W × 18″D × 42–54″H", "48 × 36 × 18″",
        "Freestanding upright chest with multiple stacked drawers and no doors. The generic term; 'dresser' implies bedroom use.",
        ("bedroom_tall_chest",),
    ),
    # ── Kitchen & Dining ──────────────────────────────────────────────────────
    (
        "Kitchen & Dining", "Hoosier cabinet", "Kitchen cabinet*",
        "40–42″W × 28″D × 68–72″H", "70 × 41 × 28″",
        "Early 20th-century American freestanding kitchen unit with upper cabinet (flour bin/spice storage) and lower cabinet with drawers.",
        ("kitchen_base_3_drawer",),
    ),
    (
        "Kitchen & Dining", "Welsh dresser", "Kitchen dresser*, Dutch dresser*, Hutch*",
        "48–60″W × 18″D × 72–84″H", "78 × 54 × 18″",
        "British two-part kitchen piece with open plate-display shelves above and drawers/cabinet doors below. Equivalent to a hutch.",
        (),
    ),
    (
        "Kitchen & Dining", "Dutch dresser", "Welsh dresser*, Kitchen dresser*",
        "48–60″W × 18″D × 72–84″H", "78 × 54 × 18″",
        "American term equivalent to Welsh dresser. A freestanding kitchen hutch with shelves above and drawers/cabinets below.",
        (),
    ),
    (
        "Kitchen & Dining", "Pie safe", "Jelly cupboard*",
        "36–42″W × 18″D × 48–60″H", "54 × 38 × 18″",
        "19th-century American food storage cabinet with punched tin ventilation panels in the doors; drawers in the base.",
        (),
    ),
    (
        "Kitchen & Dining", "Jelly cupboard", "Pie safe*",
        "30–36″W × 16″D × 48–54″H", "50 × 32 × 16″",
        "Simple country cabinet with one or two doors and drawers; used for storing preserves. Similar to pie safe but without tin panels.",
        ("storage_wall_cabinet",),
    ),
    (
        "Kitchen & Dining", "Pantry cupboard", "Step-back cupboard*",
        "36–48″W × 18″D × 72–84″H", "78 × 42 × 18″",
        "Tall freestanding pantry storage cabinet with doors and drawers; used in kitchens and farmhouses for dry goods.",
        ("kitchen_tall_pantry",),
    ),
    (
        "Kitchen & Dining", "Step-back cupboard", "Pantry cupboard*",
        "42–54″W × 20″D × 78–84″H", "81 × 48 × 20″",
        "Two-part piece where upper section steps back from lower. Drawers and doors below; doors or open shelves above.",
        (),
    ),
    (
        "Kitchen & Dining", "Apothecary cabinet", "Apothecary chest*",
        "24–48″W × 14″D × 36–60″H", "48 × 36 × 14″",
        "Originally a druggist's piece with many small labeled drawers. Used decoratively today for hardware/spices/crafts.",
        ("workshop_tool_chest",),
    ),
    (
        "Kitchen & Dining", "Dry sink", "—",
        "36–48″W × 20″D × 32–36″H", "34 × 42 × 20″",
        "19th-century American piece with a recessed top for a basin; cabinet doors below and sometimes drawers. Pre-plumbing predecessor to the kitchen sink cabinet.",
        (),
    ),
    # ── Entryway & Living Room ────────────────────────────────────────────────
    (
        "Entryway & Living Room", "Hall console", "Entry table*",
        "48–60″W × 14″D × 30–36″H", "33 × 54 × 14″",
        "Narrow entryway table with one or two drawers and sometimes cabinet doors below; sits flush against a wall.",
        ("foyer_console_2_drawer", "foyer_console_narrow"),
    ),
    (
        "Entryway & Living Room", "Entry cabinet", "Hall console*",
        "30–48″W × 14″D × 30–36″H", "33 × 40 × 14″",
        "Storage cabinet for entryways with doors and drawers for keys and mail. May include a bench or hooks.",
        ("entryway_entry_cabinet",),
    ),
    (
        "Entryway & Living Room", "Hall tree", "—",
        "30–48″W × 16″D × 72–80″H", "76 × 38 × 16″",
        "Tall entry piece combining coat hooks, a mirror, and a lower storage bench or cabinet with drawers.",
        ("entryway_hall_tree",),
    ),
    (
        "Entryway & Living Room", "Entertainment center", "Media center, TV stand*",
        "60–84″W × 18″D × 60–84″H", "72 × 72 × 18″",
        "Large wall unit combining open shelving, a TV bay, and cabinet doors with drawers for A/V equipment and media.",
        ("media_console",),
    ),
    (
        "Entryway & Living Room", "Media console", "TV stand*, Credenza*",
        "48–72″W × 18″D × 24–30″H", "27 × 60 × 18″",
        "Low cabinet for TV and A/V equipment with cabinet doors and sometimes drawers. Lower-profile evolution of the entertainment center.",
        ("media_console",),
    ),
    (
        "Entryway & Living Room", "Cocktail cabinet", "Bar cabinet, Drinks cabinet*",
        "24–36″W × 16″D × 36–48″H", "42 × 30 × 16″",
        "Cabinet for storing and serving drinks with fold-down bar surface; interior bottle storage and drawers for accessories.",
        ("living_room_bar_cabinet",),
    ),
    (
        "Entryway & Living Room", "Bar cabinet", "Cocktail cabinet*, Tantalus cabinet*",
        "24–48″W × 16″D × 30–48″H", "42 × 36 × 16″",
        "Cabinet for storing and serving drinks; ranges from a small lockable piece to a full unit with drawers and wine storage.",
        ("living_room_bar_cabinet",),
    ),
    (
        "Entryway & Living Room", "Tantalus cabinet", "Bar cabinet*, Cocktail cabinet*",
        "18–24″W × 14″D × 28–36″H", "32 × 20 × 14″",
        "Lockable drinks cabinet; historically allowed decanters to be seen but not accessed. Modern versions are decorative lockable liquor cabinets.",
        ("living_room_bar_cabinet",),
    ),
    (
        "Entryway & Living Room", "Corner cabinet", "Encoignure*",
        "24–36″W × 24″D × 60–84″H", "72 × 30 × 30″",
        "Triangular or angled cabinet for room corners; with doors and sometimes drawers. Can be freestanding or built-in.",
        (),
    ),
    (
        "Entryway & Living Room", "Encoignure", "Corner cabinet*",
        "22–30″W × 22″D × 30–36″H", "33 × 26 × 26″",
        "French term for a corner cabinet; typically a smaller lower antique piece with a door and shelf.",
        (),
    ),
    (
        "Entryway & Living Room", "Bookcase with cabinet base", "Library cabinet*",
        "30–48″W × 14″D × 72–84″H", "78 × 36 × 14″",
        "Open bookshelves above; closed cabinet doors with drawers below. Display storage above and concealed storage below.",
        ("storage_wall_cabinet",),
    ),
    # ── Bathroom ─────────────────────────────────────────────────────────────
    (
        "Bathroom", "Bathroom vanity", "Vanity cabinet*",
        "24–72″W × 21″D × 32–36″H", "34 × 48 × 21″",
        "Bathroom base cabinet supporting a sink; drawers and cabinet doors below for toiletry storage.",
        ("bathroom_vanity",),
    ),
    (
        "Bathroom", "Medicine cabinet", "—",
        "14–30″W × 4″D × 20–30″H", "25 × 24 × 4″",
        "Wall-mounted cabinet with mirrored door and interior shelves; typically recessed into the wall above a sink.",
        (),
    ),
    (
        "Bathroom", "Linen cabinet", "Linen tower*",
        "18–24″W × 14″D × 60–84″H", "72 × 21 × 14″",
        "Tall narrow freestanding cabinet for bathroom storage with doors and shelves; sometimes a base drawer.",
        ("bathroom_linen_tower",),
    ),
    (
        "Bathroom", "Linen tower", "Linen cabinet*",
        "18–24″W × 14″D × 66–84″H", "75 × 21 × 14″",
        "Tall freestanding bathroom storage unit; effectively synonymous with linen cabinet. 'Tower' emphasizes the narrow tall profile.",
        ("bathroom_linen_tower",),
    ),
    (
        "Bathroom", "Bathroom armoire", "Linen cabinet*, Armoire*",
        "30–40″W × 16″D × 66–80″H", "74 × 36 × 16″",
        "Freestanding armoire-style cabinet adapted for bathroom use with shelves and drawers for towels and toiletries.",
        ("bathroom_linen_tower",),
    ),
    # ── Office & Desk ─────────────────────────────────────────────────────────
    (
        "Office & Desk", "Filing cabinet", "File cabinet",
        "15–18″W × 28″D × 28–52″H", "52 × 18 × 28″",
        "Office cabinet with deep drawers for letter or legal files; typically in 2- or 4-drawer vertical configurations.",
        ("office_filing_cabinet",),
    ),
    (
        "Office & Desk", "Lateral file cabinet", "Filing cabinet*",
        "30–42″W × 20″D × 28–52″H", "52 × 36 × 20″",
        "Filing cabinet with wide shallow drawers holding files side-to-side. More wall-efficient than vertical filing cabinets.",
        ("office_filing_cabinet",),
    ),
    (
        "Office & Desk", "Pedestal desk", "Partners desk*",
        "54–72″W × 30″D × 29–30″H", "30 × 60 × 30″",
        "Writing desk supported by two side pedestals each containing drawers and often a cabinet door.",
        (),
    ),
    (
        "Office & Desk", "Partners desk", "Pedestal desk*",
        "60–84″W × 48″D × 29–30″H", "30 × 72 × 48″",
        "Oversized double-sided pedestal desk for two people facing each other; each side has its own drawers and pedestals.",
        (),
    ),
    (
        "Office & Desk", "Davenport desk", "—",
        "20–24″W × 20″D × 33–40″H", "37 × 22 × 20″",
        "Small Victorian writing desk with a slant top and a column of drawers on one side. Compact and ornate.",
        (),
    ),
    (
        "Office & Desk", "Campaign desk", "—",
        "40–48″W × 22″D × 30″H", "30 × 44 × 22″",
        "Portable folding desk with recessed hardware and removable legs for flat packing. Historically used by military officers in the field.",
        (),
    ),
    # ── Workshop & Utility ────────────────────────────────────────────────────
    (
        "Workshop & Utility", "Tool chest", "Tool cabinet*",
        "26–42″W × 18″D × 24–44″H", "35 × 36 × 18″",
        "Cabinet for tool storage with a combination of deep and shallow drawers and sometimes cabinet doors for larger tools.",
        ("workshop_tool_chest",),
    ),
    (
        "Workshop & Utility", "Machinist's cabinet", "Tool chest*",
        "28–36″W × 20″D × 36–48″H", "42 × 32 × 20″",
        "Precision cabinet with many small shallow drawers for organizing machining tools and measuring instruments.",
        ("workshop_tool_chest",),
    ),
    (
        "Workshop & Utility", "Plan chest", "Flat file cabinet",
        "36–50″W × 26″D × 15–40″H", "30 × 44 × 26″",
        "Wide very-shallow-drawer cabinet for storing flat plans, drawings, maps, and large-format documents.",
        (),
    ),
    (
        "Workshop & Utility", "Taboret", "—",
        "16–24″W × 16″D × 28–36″H", "32 × 18 × 18″",
        "Small artist's or craftsman's cabinet with drawers and sometimes a door; used beside a workbench or easel.",
        (),
    ),
    # ── Antique & Regional ────────────────────────────────────────────────────
    (
        "Antique & Regional", "Press cupboard", "Court cupboard*",
        "48–60″W × 20″D × 56–72″H", "64 × 54 × 20″",
        "English Renaissance storage cupboard in two stages; lower enclosed section has doors and drawers; upper is open or semi-open.",
        (),
    ),
    (
        "Antique & Regional", "Court cupboard", "Press cupboard*",
        "42–54″W × 18″D × 42–54″H", "48 × 48 × 18″",
        "Lower open-tiered English Renaissance display piece with drawers in the frieze. Distinguished from press cupboard by its shorter and more open form.",
        (),
    ),
    (
        "Antique & Regional", "Trumeau", "—",
        "18–30″W × 6″D × 60–80″H", "72 × 24 × 6″",
        "French mirror cabinet combining a mirror above with a small cabinet or drawers below. Historically placed between windows.",
        (),
    ),
    (
        "Antique & Regional", "Tansu", "—",
        "36–54″W × 16″D × 36–72″H", "54 × 42 × 16″",
        "Japanese stepped or tiered storage chest traditionally in stacked sections. Combines small doors, drawers, and open shelves in asymmetric arrangements.",
        (),
    ),
    (
        "Antique & Regional", "Bandaji", "—",
        "36–48″W × 20″D × 18–24″H", "20 × 42 × 20″",
        "Korean chest that opens at the top half of the front face while the lower half is fixed. Used for blankets and clothing; may have small base drawers.",
        (),
    ),
]


# ── Build catalogue ───────────────────────────────────────────────────────────

FURNITURE_REFS: list[FurnitureRef] = []
for _cat, _piece, _syns_raw, _typical, _example, _desc, _presets in _RAW:
    _h, _w, _d = _parse_example(_example)
    FURNITURE_REFS.append(FurnitureRef(
        category=_cat,
        piece=_piece,
        synonyms=_syns(str(_syns_raw)),
        typical_dims=_typical,
        example_h_mm=_h,
        example_w_mm=_w,
        example_d_mm=_d,
        description=_desc,
        preset_keys=_presets,
    ))


# ── Lookup index ──────────────────────────────────────────────────────────────
# Maps normalised (lower-case, stripped) name → FurnitureRef

def _norm(s: str) -> str:
    return s.lower().strip().rstrip("*").replace("’", "’")  # curly apostrophe → straight


_INDEX: dict[str, FurnitureRef] = {}
# Two-pass build: canonical piece names first so they always win over synonyms
# from other entries that share the same word.
for _ref in FURNITURE_REFS:
    _key = _norm(_ref.piece)
    if _key:
        _INDEX.setdefault(_key, _ref)
for _ref in FURNITURE_REFS:
    for _syn in _ref.synonyms:
        _key = _norm(_syn)
        if _key and _key != "—":
            _INDEX.setdefault(_key, _ref)

# Flat mapping: normalised name → tuple of preset slugs.
# Same two-pass logic: canonical entries win over cross-reference synonyms.
SYNONYM_TO_PRESETS: dict[str, tuple[str, ...]] = {}
for _ref in FURNITURE_REFS:
    _key = _norm(_ref.piece)
    if _key:
        SYNONYM_TO_PRESETS.setdefault(_key, _ref.preset_keys)
for _ref in FURNITURE_REFS:
    for _syn in _ref.synonyms:
        _key = _norm(_syn)
        if _key and _key != "—":
            SYNONYM_TO_PRESETS.setdefault(_key, _ref.preset_keys)


# ── Public API ────────────────────────────────────────────────────────────────

def get_furniture(query: str) -> FurnitureRef | None:
    """Exact (case-insensitive) lookup by piece name or synonym."""
    return _INDEX.get(_norm(query))


def identify_furniture(query: str) -> list[FurnitureRef]:
    """
    Return matching FurnitureRef objects for ``query``.

    Tries in order:
    1. Exact match on canonical name or synonym.
    2. Prefix match.
    3. Substring match.

    Returns up to 5 candidates, deduplicated, canonical names first.
    """
    q = _norm(query)
    if not q:
        return []

    exact = _INDEX.get(q)
    if exact:
        return [exact]

    seen: set[str] = set()
    results: list[FurnitureRef] = []

    def _add(ref: FurnitureRef) -> None:
        if ref.piece not in seen:
            seen.add(ref.piece)
            results.append(ref)

    # Prefix matches
    for key, ref in _INDEX.items():
        if key.startswith(q):
            _add(ref)

    # Substring matches
    for key, ref in _INDEX.items():
        if q in key:
            _add(ref)

    return results[:5]
