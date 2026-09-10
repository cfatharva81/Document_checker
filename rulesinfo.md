# Document Validation Rules --- Base Functions & Rule Engine

## Base.py --- Common Functions Summary

  -----------------------------------------------------------------------
  Function                            Purpose
  ----------------------------------- -----------------------------------
  `Finding`                           Stores the result of a rule check.

  `Rule`                              Base interface used by individual
                                      rules.

  `RuleConfig`                        Stores configurable rule settings.

  `ok()`                              Creates a passing `Finding`.

  `fail()`                            Creates a failing `Finding`.

  `na()`                              Creates a not-evaluated `Finding`.

  `rule_metadata()`                   Provides rule information for the
                                      registry/UI.

  `normalize_key()`                   Normalizes text for comparison.

  `normalize_filename()`              Cleans a filename for title
                                      comparison.

  `normalize_title()`                 Cleans a document title for
                                      comparison.

  `similarity()`                      Calculates fuzzy text similarity.

  `digits_conflict()`                 Detects conflicting numbers or
                                      identifiers.

  `first_heading1()`                  Gets the first Heading 1.

  `find_versions()`                   Finds version numbers.

  `parse_date()`                      Parses date text.

  `find_dates()`                      Finds dates in document content.

  `has_date()`                        Checks whether date information
                                      exists.

  `iter_headings()`                   Iterates through headings.

  `is_heading()`                      Checks whether content is a
                                      heading.

  `heading_level()`                   Gets heading level information.

  `normalized_heading_text()`         Normalizes heading text.

  `table_labeled_values()`            Gets labeled values from tables.

  `table_header_cells()`              Gets table headers.

  `table_is_populated()`              Checks whether a table contains
                                      useful data.

  `header_column_index()`             Finds a column by its header.

  `tables_after_heading()`            Finds tables following a heading.

  `find_revision_heading()`           Finds a revision-history heading.

  `find_revision_table()`             Finds the revision-history table.

  `looks_like_revision_table()`       Identifies likely revision tables.

  `signature_paragraphs()`            Finds paragraph-based signature
                                      labels.

  `snippet()`                         Creates short evidence text.

  `Locator`                           Provides document location/evidence
                                      information.

  `dedupe()`                          Removes duplicate items.
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# Rule 1 --- Title / Filename Match

**Flow:**
`Filename + Titles → Normalize → Exact match → Number check → Fuzzy similarity → PASS/FAIL`

  Base function              What the rule uses it for
  -------------------------- ------------------------------
  `strip_extension()`        Removes filename extension.
  `normalize_key()`          Normalizes comparison text.
  `strip_noise()`            Removes irrelevant noise.
  `normalize_filename()`     Normalizes filename.
  `normalize_title()`        Normalizes title.
  `strip_leading_number()`   Removes leading numbering.
  `_digit_sets()`            Extracts numbers.
  `digits_conflict()`        Detects conflicting numbers.
  `similarity()`             Performs fuzzy comparison.
  `first_heading1()`         Gets the first main heading.

**Description:** Compares the filename with possible document titles. It
normalizes the values, checks exact matches, prevents conflicting
numbers from passing, and uses fuzzy similarity when needed.

------------------------------------------------------------------------

# Rule 2 --- Author Name and Role

**Flow:**
`Metadata / Tables / Body / Revision History → Find Author → Ignore Defaults → Valid Author? → PASS/FAIL`

  -----------------------------------------------------------------------
  Base function                       What the rule uses it for
  ----------------------------------- -----------------------------------
  `table_labeled_values()`            Reads author/role information from
                                      tables.

  `snippet()`                         Creates evidence.

  `ok()` / `fail()`                   Creates the result.
  -----------------------------------------------------------------------

**Description:** Looks for a valid author in metadata, information
tables, body paragraphs, and revision history. Generic/default names are
ignored.

------------------------------------------------------------------------

# Rule 3 --- Revision-History Dates

**Flow:**
`Find Revision Table → Find Date Column → Parse Dates → Check Future Dates → Check Order → PASS/FAIL`

  Base function             What the rule uses it for
  ------------------------- ---------------------------------
  `find_revision_table()`   Locates the revision table.
  `header_column_index()`   Finds the Date column.
  `parse_date()`            Parses date values.
  `find_dates()`            Finds dates when needed.
  `table_is_populated()`    Checks that the table has data.
  `snippet()`               Creates evidence.

**Description:** Checks that revision history has valid dates, dates are
not unexpectedly in the future, and revisions are in chronological
order.

------------------------------------------------------------------------

# Rule 4 --- Version Number Present

**Flow:**
`Search Document → Body/Header/Footer/Tables/Metadata → Find Versions → Version Found? → PASS/FAIL`

  Base function              What the rule uses it for
  -------------------------- ----------------------------------------
  `find_versions()`          Finds version numbers.
  `table_labeled_values()`   Reads version information from tables.
  `snippet()`                Creates evidence.
  `ok()` / `fail()`          Creates the result.

**Description:** Searches different document areas for version numbers,
including metadata, document content, tables, and revision history.

------------------------------------------------------------------------

# Rule 5 --- Revision Section Present

**Flow:**
`Find Revision Heading → Find Table After Heading → Check Populated → PASS/FAIL`

  -----------------------------------------------------------------------
  Base function                       What the rule uses it for
  ----------------------------------- -----------------------------------
  `find_revision_heading()`           Finds the revision-history heading.

  `tables_after_heading()`            Finds tables below the heading.

  `table_is_populated()`              Checks table content.

  `find_revision_table()`             Provides fallback revision-table
                                      detection.
  -----------------------------------------------------------------------

**Description:** Verifies that a revision-history section exists and
contains a populated table. A populated revision table elsewhere can
provide a fallback.

------------------------------------------------------------------------

# Rule 6 --- Signature Blocks Present

**Flow:**
`Search Signature Content → Paragraph / Signature Table → Check Structure → Genuine Block? → PASS/IGNORE`

  Base function              What the rule uses it for
  -------------------------- -------------------------------------------
  `signature_paragraphs()`   Finds signature-related paragraph labels.
  `table_header_cells()`     Reads signature table headers.
  `table_is_populated()`     Checks signature table content.
  `snippet()`                Creates evidence.

**Description:** Looks for genuine signature or approval blocks.
Structured signature tables are strong evidence; ordinary sentences
containing "approved by" should not automatically be treated as
signature blocks.

------------------------------------------------------------------------

# Rule 7 --- Dates Near Signature Blocks

**Flow:**
`Find Signature Blocks → Same Line/Table Row → Nearby Paragraphs → Date for Every Block? → PASS/FAIL`

  Base function              What the rule uses it for
  -------------------------- --------------------------------------
  `signature_paragraphs()`   Identifies signature-related blocks.
  `find_dates()`             Finds nearby dates.
  `has_date()`               Checks date presence.
  `snippet()`                Creates evidence.
  `Locator`                  Helps identify document locations.

**Description:** Checks that genuine signature blocks have an associated
date, first in the same line/table row and then in nearby content.

------------------------------------------------------------------------

# Rule 8 --- Font and Spacing Consistency

**Flow:**
`Collect Body Paragraphs → Exclude Titles/Headings/Lists/Tables → Find Dominant Style → Compare → Within Tolerance? → PASS/FAIL`

  Base function       What the rule uses it for
  ------------------- -------------------------------
  `is_heading()`      Excludes headings.
  `heading_level()`   Identifies heading levels.
  `iter_headings()`   Iterates through headings.
  `snippet()`         Creates formatting evidence.
  `Locator`           Provides paragraph locations.

**Description:** Establishes the dominant body formatting and compares
normal body paragraphs against it. Cover/title content and specialized
elements should not be treated as ordinary body paragraphs.

------------------------------------------------------------------------

# Rule 9 --- Language Errors

**Flow:**
`Extract Text → Language Checker → Filter Known Vocabulary → Genuine Error? → PASS/FAIL`

  Base function       What the rule uses it for
  ------------------- ------------------------------------------
  `LanguageChecker`   Defines the language-checking interface.
  `snippet()`         Creates evidence around errors.
  `dedupe()`          Removes duplicate findings.

**Description:** Sends document text through the configured language
checker. Domain terms, identifiers, and valid language variants should
be configurable to prevent false positives.

------------------------------------------------------------------------

# Rule 10 --- Required Sections

**Flow:**
`Configured Required Sections → Find Headings → Section Found? → PASS/FAIL`

  Base function                 What the rule uses it for
  ----------------------------- -----------------------------
  `iter_headings()`             Searches document headings.
  `normalized_heading_text()`   Normalizes heading names.
  `is_heading()`                Identifies headings.
  `snippet()`                   Creates evidence.

**Description:** Checks whether configured required sections exist. If
none are configured, the rule is not evaluated.

------------------------------------------------------------------------

# Rule 11 --- Page Numbers

**Flow:**
`Inspect Footers → Find PAGE Field → Dynamic Page Number? → PASS/FAIL`

  Base function   What the rule uses it for
  --------------- -----------------------------------------
  `snippet()`     Creates footer evidence.
  `Locator`       Provides document location information.

**Description:** Checks footers for a dynamic `PAGE` field and
identifies likely hardcoded page numbers. DOCX structure does not
directly provide final rendered pagination.

------------------------------------------------------------------------

# Rule 12 --- Readability

**Flow:**
`Extract Body Text → Calculate Scores → Flesch + Gunning Fog → Compare Thresholds → PASS/FAIL`

  Base function    What the rule uses it for
  ---------------- ---------------------------
  `is_heading()`   Helps exclude headings.
  `snippet()`      Creates evidence.

**Description:** Calculates readability metrics from body text and
compares them with configured Flesch Reading Ease and Gunning Fog
thresholds.

------------------------------------------------------------------------

# Rule 13 --- Footer Details

**Flow:**
`Inspect Footers → Document ID? → Confidentiality? → Page Number? → All Present? → PASS/FAIL`

  Base function   What the rule uses it for
  --------------- --------------------------------
  `snippet()`     Creates footer evidence.
  `Locator`       Provides location information.

**Description:** Checks that footers contain the required document ID,
confidentiality information, and page numbering.

------------------------------------------------------------------------

# How the Rule Engine Calls the Rules

**Flow:**
`Application/API → Rule Engine → REGISTRY → Rules 1–13 → Findings → Results → API/UI`

The rule engine is the central coordinator.

  -----------------------------------------------------------------------
  Function                            Role
  ----------------------------------- -----------------------------------
  `_MODULES`                          Holds the rule modules.

  `REGISTRY`                          Maps rule IDs to their `RULE`
                                      objects.

  `all_rules()`                       Returns all registered rules.

  `get_rule()`                        Retrieves one rule by ID.

  `rules_metadata()`                  Provides rule information for
                                      consumers such as the UI/API.

  `evaluate_all()`                    Runs all registered rules and
                                      collects their findings.

  `run_rule()`                        Runs one rule safely and handles
                                      exceptions.
  -----------------------------------------------------------------------

### Execution

``` text
evaluate_all(doc)
      ↓
 Rule 1 → Finding
      ↓
 Rule 2 → Finding
      ↓
 Rule 3 → Finding
      ↓
    ...
      ↓
Rule 13 → Finding
      ↓
Collect Findings
      ↓
Return Results
```

If one rule crashes, `run_rule()` catches the exception and returns an
informational `Finding` instead of stopping the complete document
analysis.

## Overall Architecture

``` text
DOCX
  ↓
Extractor
  ↓
Internal Doc Model
  ↓
Rule Engine
  ↓
Rules 1–13
  ↓
Findings
  ↓
API / UI
```

**Key idea:** `base.py` provides reusable building blocks, each rule
performs one validation task, and the rule engine manages and safely
executes the rules.
