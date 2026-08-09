"""Shared, synthetic (non-real) invoice text used across unit tests."""

RAW_INVOICE_TEXT = (
    "Invoice Invoice No: INV-001234 Invoice Date: 09/06/2025 Customer Number: "
    "CUST-78910 Payment Term: Net30 Due Date: 10/06/2025 Example Corp Bill To: "
    "123 Innovation Drive Suite 456 TechCity, TX 75001 Sample Solutions LLC "
    "Remit To: PO Box 98765 Innovation City, CA 90210 Identifier Week End "
    "Description Worksite Hours/Units Rate Amount REG 06/07/2025 Doe, John GA "
    "5.00 150.00 750.00 REG 06/14/2025 Smith, Jane GA 6.00 150.00 900.00 REG "
    "06/21/2025 Brown, Alex GA 4.00 175.00 700.00 REG 06/28/2025 Taylor, Sam "
    "GA 3.00 175.00 525.00"
)

AGENT1_MATCHING_OUTPUT = [
    {
        "invoice_number_1": "INV-001234",
        "invoice_date_1": "09/06/2025",
        "vendor_name_1": None,
        "contractor_name_1": "Doe, John",
        "date_or_range_1": "06/07/2025",
        "hours_1": 5.0,
        "rate_1": 150.0,
        "bill_amount_1": 750.0,
    }
]

AGENT2_MATCHING_OUTPUT = [
    {
        "invoice_number": "INV-001234",
        "invoice_date": "09/06/2025",
        "vendor_name": None,
        "contractor_name": "Doe, John",
        "date_or_range": "06/07/2025",
        "hours": 5.0,
        "rate": 150.0,
        "bill_amount": 750.0,
    }
]

AGENT2_MISMATCHED_OUTPUT = [
    {
        "invoice_number": "INV-001234",
        "invoice_date": "09/06/2025",
        "vendor_name": None,
        "contractor_name": "Doe, John",
        "date_or_range": None,  # disagreement vs agent 1
        "hours": 5.0,
        "rate": 150.0,
        "bill_amount": 750.0,
    }
]
