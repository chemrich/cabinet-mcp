# Assembly instructions

> Generate assembly instructions for the sideboard project.

`generate_assembly_instructions` turns a saved project into a printable carcass-assembly document — HTML and PDF, written to `~/.cabineteer/assembly/<project>/`. It covers the carcass glue-up (the part where sequence and mortise layout actually matter); drawer boxes and hardware installation follow the cutlist and hardware docs.

Identical cabinets in a run collapse into one set of instructions marked ×N, and every panel is referred to by the **same part ID it carries in the project cutlist**, so the pile of parts by your bench maps straight onto the steps.

## What's in the document

**Joint census.** Every carcass joint, counted the same way the hardware BOM counts tenons: top and bottom get four joints each, plus two per divider and two per fixed shelf. If the BOM says 28 Dominos, the census shows you the 14 joints they go into.

**Mortise positions measured from the front edge.** For floating-tenon carcasses, mortise centres come from the same spacing rule the BOM uses, measured from the FRONT edge on **both** mating parts — the single convention that keeps a divider from going in offset. Tenon size follows stock thickness: 5 × 30 mm for stock up to 19 mm, 8 × 40 mm above.

**One registration system in the thickness direction too.** Every slot sits **10 mm from a marked reference face** (top/bottom: outside face; shelves: underside; dividers: left face) — 10 mm because that's the DF 500's *fixed* base height, the only registration available for face mortises mid-panel. The fence is therefore set to 10 mm to match (a 0-offset base plate like the Seneca Domiplate is the same setting), **not** centred at t/2: centring the edge slots while the face slots ride the base puts the two halves of a joint 1 mm out of plane in 18 mm stock, and a tight-width Domino joint won't close. Slots land slightly off-centre in the stock — intentional and harmless. Stock under 15 mm falls back to centred slots with an explicit batten offset in the machine table.

**Machine setup block.** For a Festool DF 500: cutter, plunge depth, the 10 mm fence/registration setting, and the batten lines for face rows.

**Registration section with drawings.** Every generated doc includes a "Registration — how the two halves of a joint line up" section: three cross-section drawings (cutting the face slots · cutting the edge slots · the assembled joint) that make the shared 10 mm reference visible. The labels adapt to the build — divider, fixed shelf, or plain corner.

### Worked example: an internal divider

Say a divider's left face belongs 582.6 mm from the left end of the bottom panel (the mortise maps mark these left-face lines for you):

1. **On the bottom (and top) panel** — strike a line across the panel at 582.6 mm, square off the front edge. Clamp a straight batten *on* the line, on the side away from where the divider will stand. Stand the DF 500 on its base inside the divider's footprint, butt it against the batten, and plunge at each centre mark. The cutter axis lands 10 mm past the line — at 592.6 — because 10 mm is the machine's fixed base height.
2. **On the divider** — mark its LEFT face. Ride the fence (set to 10 mm) or a 0-offset Domiplate on that face and plunge into both ends. Those slots also sit 10 mm from the left face.
3. **Assembly** — the tenons line up because both cuts measured 10 mm from the same reference, and the divider's left face lands exactly on your 582.6 line. No arithmetic at the bench, and the slot being 1 mm off-centre in the stock is irrelevant — don't "fix" it.

A shelf is the same drawing rotated: the reference is the shelf's **underside** line on the side panel (or divider) it joins. A corner is the same again with the line at the panel **end**.

**Per-panel mortise maps.** A drawing per panel showing every mortise on it — face mortises in red, edge mortises in blue — so you can lay a panel on the bench and drill everything it needs in one session.

**Consumables list.** Tenon count with pack sizes, glue, and a suggested count of 3D-printed PETG dry-fit tenons (printables.com model 689403) — snug test tenons you can pull back out, which make the dry-fit step far less nerve-wracking than using real Dominos dry.

**An ordered step list where the dry fit is not optional.** A complete no-glue dry assembly always precedes glue-up. If something is wrong, you find out while it still costs nothing.

## Mitered carcasses

If the project uses mitered waterfall corners (see [joinery.md](joinery.md)), the document adapts:

- The four corner joints become miter joints (purple in the maps); side-panel rows move to the beveled ends, and top/bottom maps go long-point wide with divider centrelines shifted accordingly.
- The machine table gains fence-at-45° rows with the solved mortise placement in the beveled face — including the wall-thickness check that keeps the plunge from exiting the show face.
- A dedicated step has you **dial in the miter mortise on scrap** before touching a real panel.
- Glue-up switches technique: tape-hinge the miters, close the box, band clamps.

## Edge banding steps

Banding inserts itself into the sequence in the mode-correct place ([edge-banding.md](edge-banding.md)):

- **Hardwood banding happens BEFORE mortising** — the banded front edge is the mortise reference edge.
- **Hot-melt ironing happens AFTER glue-up and cure.**
