# Measurement reference

Plugin id: `org.radspider.measurement-reference` · folder: [`../../org.radspider.measurement-reference`](../../org.radspider.measurement-reference)

TL;DR: a searchable guide of radiological measurements in a window of its own. Each entry says what is measured,
how to draw it, the reference values, the source, and shows one picture. Entries are Markdown files: 71 are shipped,
and the user adds or replaces them in a folder of their own. `api = 6`, Pillow. One tool, `guide`, icon `ruler`.

| Topic | |
|---|---|
| Open it | Ribbon *Advanced → Plugins → Measurement reference*. It is an image tool (`input = "image"`): the button is grey until the active viewport shows an acquired image |
| Search | *Search* field: every word must occur in the title, region, keywords or text of the entry; case and accents are ignored (`bohler` finds *Böhler*). Entries whose title holds every word come first. *Region* narrows the list |
| Pick | *Measurement (n)* lists the matches. A new search shows its first match; a pick stays until the next search |
| Window | `window.reuse`: a second click on the ribbon button goes to the open window. Sections (*How to measure*, *Values*, *Source*) collapse |
| Languages | English only: entries, labels and search keywords (many entries carry Spanish keywords). No `lang/` catalog |

## Entries are files

| Folder | What | Survives a plugin update |
|---|---|---|
| `<plugins>/org.radspider.measurement-reference/references/` | The shipped entries and `images/` | No: the update replaces the folder |
| `~/radspider-references/` (or the folder named by `RADSPIDER_REFERENCE_DIR`) | The user's entries. Created on first run with `_template.md` in it | Yes |

- One `.md` file per measurement. A file in the user's folder with the same name as a shipped one replaces it.
- Files whose name starts with `_` are not entries (`_template.md`, `_credits.md`).
- The window shows the path of the file of the entry on screen and of the user's folder.
- A change shows on the next search, pick or ribbon click: every run reads the files again.

Format (`references/_template.md` is a working example):

| Line | Becomes |
|---|---|
| `# Title` (first one) | The entry's name in the list |
| `Region: …`, `Keywords: …` | The region filter; extra words for the search. Both optional |
| `![caption](images/file.jpg)` (first one) | The picture, path relative to the file; PNG or JPEG, shrunk to 1000 px |
| `## Heading` | A collapsible section |
| Lines starting with `\|` | A table (the `\|---\|` row is dropped) |
| `- item` | A bullet |
| Anything else | Plain text; `**` and backticks are removed, other Markdown shows as written |

The host has no Markdown widget, so this is a subset drawn with labels, tables, sections and one picture.

## Shipped entries

71, by region: Hip 13, Abdomen 11, Spine 8, Foot and ankle 6, Wrist 6, Obstetrics 5, Chest 4, Brain 3, Elbow 3,
Head and neck 2, Lower limb 2, Oncology 2, Pelvis 2, Bone density 1, Knee 1, Shoulder 1, Vascular 1.

| Topic | |
|---|---|
| Text | Written for this plugin; values and their sources are named in each entry's *Source* section |
| Pictures | From Wikimedia Commons, one per entry, only CC0, public domain, CC BY or CC BY-SA. Author, licence and link are in each entry and in `references/_credits.md` |
| Changes to pictures | Resized to at most 800 px, saved as JPEG, transparent line art put on white. The nuchal translucency picture had its header band (operator name, exam date) cropped |
| Licence | The pictures are **not** under this repository's `LICENSE`: each keeps its own (the CC BY-SA ones stay CC BY-SA). The texts and the code are under `LICENSE` |
| Patient data | The pictures are published, de-identified teaching images. Each was looked at for burned-in names, dates of birth and IDs; none was found. Two show an exam date or scanner settings (bladder volume, Haller index) |
| Not shipped | Measurements for which no picture with a usable licence was found, among them: Powers ratio, basion–dens interval, Torg–Pavlov ratio, pelvic incidence, Chamberlain and McGregor lines, femoral anteversion, Caton–Deschamps, Blackburne–Peel, TT–TG distance, sulcus angle, tibial slope, Kite angle, ankle clear spaces, carpal height ratio, critical shoulder angle, glenoid version, pulmonary artery and RV/LV ratios, Chiari tonsil position, ABC/2, pyloric stenosis, prostate volume, fetal head and abdominal circumference, femur length, amniotic fluid index. Add them as your own entries |

## Limits

- **Not a medical device.** A memory aid: thresholds differ between sources, populations and techniques. Check the cited source before relying on a value.
- The reference values were written from the cited literature by the author of the entries and have **not** been reviewed by a radiologist. One was checked against the paper's abstract (prevertebral soft tissue, Rojas 2009), and that check found the picture's C2 label wrong (the entry says so).
- Needs an acquired image on screen, although it reads no pixels: a tool cannot run without an input, and one image costs less per search than a volume. It does not open on an MPR, slab or MIP plane.
- Each search or pick starts Python again (about 0.1–0.3 s plus the picture).
- One picture per entry. No links, no bold, no nested lists.

## Verified

| | |
|---|---|
| Verified (1.0.0) | **Not run in radspider.** Run outside the viewer with Python 3.13 and Pillow 12.3: (1) through the SDK's own host script (`_radspider_host.py` from radspider `assets/python`, one JSON request on stdin with a 2 × 2 image) three times — first run, a search (`bohler` → *Böhler angle*), a search without matches — each reply read back as JSON with the expected blocks, and the user folder created with its template; (2) `python -m unittest tools.test_measurement_reference` (6 tests, a stand-in for the SDK): every shipped entry has a title, a region, a picture that decodes and a stated picture licence; search order, case and accents; Markdown to tables and labels; a user file replaces a shipped one; the pick stays until a new search; (3) `tools/validate_plugins.py`, `ruff check`. **Not checked:** the radspider host accepting the reply (its Rust-side limits), how labels, tables and pictures look in the window, the ribbon button, `window.reuse`, Windows and macOS paths. Every picture was viewed once at reduced size; licences were read on each Commons file page by a research pass, not re-read afterwards. |
