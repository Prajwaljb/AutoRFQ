# Product data

The data AutoRFQ falls back on when ferguson.com cannot be read, and the specs it reads documents with.

Live lookups first read each product from ferguson.com. The site blocks many automated visits, so if a lookup
is blocked or times out, the same product is read from this catalog and the run carries on. Every value taken
from here is marked with its source, like any other value.

The data was collected from ferguson.com on 24 September 2026. Prices and stock may have changed since, so
replies label catalog prices as list prices from that date.

## Files

| File | What it is |
|---|---|
| `product_catalog.csv` | One row per product, 56 products, 32 columns. Open in any tool. |
| `product_catalog.json` | The same data as JSON, keyed by `product_id`. What the code loads. |
| `product_catalog_sources.csv` | Where every value came from: one row per filled value, with its source type, confidence and source. Reproduces the Sources sheet of the reference RFQ. |
| `spec_sheet_links.csv` | The manufacturer spec sheet PDF for 39 of the products. These download live and are read for Thickness, ASTM, OSHA and Material. |
| `spec_cache/` | Bundled copies of 8 spec sheet PDFs, so `--no-browser` runs are repeatable when a download fails. |
| `product_catalog.xlsx` | All of the above in one workbook, plus a sheet of products that are not in the catalog (old Ferguson items, used to describe a Not found item). For reading, not for the code. |

## Columns

| Group | Columns |
|---|---|
| Identity | `product_id`, `Description`, `Brand`, `Manufacturer Part #`, `Ferguson Part #`, `UPC`, `Category`, `Product Family`, `Tool Type` |
| Physical specification | `Length`, `Width`, `Thickness`, `Weight`, `Material`, `Material Type`, `Color Finish`, `Lettering`, `No of Tools`, `Application`, `Temperature Range`, `Product details`, `Waterworks Application` |
| Compliance | `ANSI`, `ASTM`, `OSHA`, `UL Listed` |
| Commercial | `Price (USD)`, `Availability`, `Status` |
| Evidence and media | `Picture URL`, `Ferguson URL`, `Spec Sheet URL` |

Lists inside one cell are separated by `|` (for example several ASTM standards).
