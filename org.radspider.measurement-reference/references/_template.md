# Name of the measurement
Region: Spine
Keywords: synonyms, eponyms, words in your language that the search should find

One or two lines that say what it measures and on which image. This part is shown above the picture.

![What the picture shows](images/your-picture.png)

## How to measure

- One step per line.
- Paths of pictures are relative to this file; PNG and JPEG work. One picture per entry.

## Values

| Finding | Value |
|---|---|
| Normal | < 10° |
| Abnormal | ≥ 10° |

## Source

Author, journal, year. Picture: author, licence, link.


## How entries work

- One Markdown file per measurement in this folder. Files whose name starts with "_" are ignored.
- "# " is the title; "Region:" and "Keywords:" are optional; "## " starts a collapsible section;
  lines starting with "|" make a table; "- " makes a bullet. Other Markdown is shown as plain text.
- A file here with the same name as a shipped one replaces it, and plugin updates do not touch this folder.
- The search looks at the title, region, keywords and the whole text, ignoring case and accents.

