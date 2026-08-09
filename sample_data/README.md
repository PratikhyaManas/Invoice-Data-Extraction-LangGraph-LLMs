# sample_data

Drop synthetic (never real) sample invoice PDFs here for local testing,
e.g. `sample_invoice.pdf`. This directory is gitignored for PDFs so
real invoice data never accidentally gets committed.

For automated tests, prefer `tests/fixtures/sample_invoice_text.py`,
which already contains synthetic invoice text and expected agent
outputs and does not require a PDF file at all.
