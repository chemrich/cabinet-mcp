# Assembly instructions

> Generate assembly instructions for the sideboard project.

`generate_assembly_instructions` turns a saved project into a printable carcass-assembly document — HTML and PDF, written to `~/.cabineteer/assembly/<project>/`. It covers the carcass glue-up (the part where sequence and mortise layout actually matter); drawer boxes and hardware installation follow the cutlist and hardware docs.

Identical cabinets in a run collapse into one set of instructions marked ×N, and every panel is referred to by the **same part ID it carries in the project cutlist**, so the pile of parts by your bench maps straight onto the steps.

## What's in the document

**Joint census.** Every carcass joint, counted the same way the hardware BOM counts tenons: top and bottom get four joints each, plus two per divider and two per fixed shelf. If the BOM says 28 Dominos, the census shows you the 14 joints they go into.

**Mortise positions measured from the front edge.** For floating-tenon carcasses, mortise centres come from the same spacing rule the BOM uses, measured from the FRONT edge on **both** mating parts — the single convention that keeps a divider from going in offset. Tenon size follows stock thickness: 5 × 30 mm for stock up to 19 mm, 8 × 40 mm above.

**Machine setup block.** For a Festool DF 500: cutter, plunge depth, fence height, and a per-thickness fence schedule when the build mixes stock.

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
