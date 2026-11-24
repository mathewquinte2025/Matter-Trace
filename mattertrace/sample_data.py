"""Synthetic demo data. Every name, date, number, and organization here is fictional."""

DEMO_PASSWORD = "demo123"

MATTERS = [
    # matter_id, display_label, client_name, client_dob, incident_date, claim_number, insurer
    ("MT-1001", "Reyes v. Coastal Freight", "Daniel Reyes", "03/14/1985", "06/02/2025", "CF-88213-A", "Harborline Mutual"),
    ("MT-1002", "Okafor v. Sunrise Grocers", "Grace Okafor", "11/02/1990", "08/19/2025", "SG-55107", "Palmetto Casualty"),
    ("MT-1003", "Lindqvist v. Metro Transit", "Erik Lindqvist", "07/22/1978", "09/30/2025", "MTA-30442", "Keystone Public Risk"),
    # Deliberately similar client name to MT-1001 for false-match testing.
    ("MT-1004", "Reyes v. Bayside Apartments", "Daniela Reyes", "05/09/1992", "04/11/2025", "BA-71920", "Harborline Mutual"),
]

USERS = [
    # user_id, username, display_name, role, permitted matters
    ("U-PAT", "pat", "Pat Morgan (Paralegal)", "paralegal", ["MT-1001", "MT-1002", "MT-1004"]),
    ("U-RILEY", "riley", "Riley Chen (Paralegal)", "paralegal", ["MT-1003"]),
    ("U-AVERY", "avery", "Avery Brooks (Supervising Attorney)", "attorney", ["MT-1001", "MT-1002", "MT-1003", "MT-1004"]),
    ("U-CASEY", "casey", "Casey Diaz (Intake Clerk)", "intake", ["MT-1001", "MT-1002", "MT-1003", "MT-1004"]),
]

REYES_ER_BILL_PAGES = [
    "GULF COAST MEDICAL CENTER - EMERGENCY DEPARTMENT\n"
    "ITEMIZED STATEMENT\n"
    "\n"
    "Invoice No: INV-44817\n"
    "Patient: Daniel Reyes\n"
    "Date of Birth: 03/14/1985\n"
    "Date of Service: 06/02/2025\n"
    "Insurance Claim: CF-88213-A\n"
    "\n"
    "ED visit, level 4 ............ $1,450.00\n"
    "CT scan, cervical spine ....... $890.00\n"
    "\n"
    "Total Charges: $2,340.00\n"
    "Amount Due: $2,340.00\n"
    "\n"
    "SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD"
]

OKAFOR_LETTER = """PALMETTO CASUALTY INSURANCE COMPANY
Claims Department

September 15, 2025

Re: Our insured Sunrise Grocers
Claimant: Grace Okafor
Claim Number: SG-55107
Date of Loss: 08/19/2025

Dear Counsel,

We acknowledge receipt of your letter of representation regarding the above claimant.
Please forward all medical records and billing related to the incident of 08/19/2025
so that we may complete our evaluation. Kindly reference the claim number on all
correspondence. Our adjuster assigned to this file will contact your office within
thirty days.

Sincerely,
J. Whitfield, Claims Adjuster

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
"""

LINDQVIST_PT = """NORTHSIDE PHYSICAL THERAPY
Progress Note

Patient: Erik Lindqvist
DOB: 07/22/1978
Date of injury: 09/30/2025
Referring claim: MTA-30442

Patient reports reduced lower back pain since initial evaluation. Range of motion
improved. Continue plan of care two times per week for four weeks.

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
"""

DANIELA_INCIDENT = """BAYSIDE APARTMENTS - INCIDENT REPORT

Resident: Daniela Reyes
Date of birth: 05/09/1992
Incident date: 04/11/2025
Description: Resident reported a fall on the exterior stairwell near building C.

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
"""

# Existing confirmed records that new uploads are compared against.
# (filename, matter_id, kind, content, submitting user, source_type)
EXISTING_DOCUMENTS = [
    ("Reyes_ER_Bill_INV-44817.pdf", "MT-1001", "pdf", REYES_ER_BILL_PAGES, "U-PAT", "Provider portal"),
    ("Okafor_Insurer_Ack_Letter.txt", "MT-1002", "txt", OKAFOR_LETTER, "U-PAT", "Mail"),
    ("Lindqvist_PT_Progress_Note.txt", "MT-1003", "txt", LINDQVIST_PT, "U-RILEY", "Provider portal"),
    ("Daniela_Reyes_Incident_Report.txt", "MT-1004", "txt", DANIELA_INCIDENT, "U-PAT", "Client upload"),
]

# Sample files a user can upload in the demo. Each exercises one scenario.
SAMPLE_UPLOADS = {
    "01_clear_match_reyes_records_request.txt": """RECORDS REQUEST - ACKNOWLEDGEMENT

Patient: Daniel Reyes
Date of Birth: 03/14/1985
Claim reference: CF-88213-A

Gulf Coast Medical Center confirms receipt of your request for records related to the
emergency visit on 06/02/2025. Records will be released within 15 business days.

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
""",
    "03_conflicting_reyes_er_bill.txt": """GULF COAST MEDICAL CENTER - EMERGENCY DEPARTMENT
ITEMIZED STATEMENT (REPRINT)

Invoice No: INV-44817
Patient: Daniel Reyes
Date of Birth: 03/14/1985
Date of Service: 06/02/2025

ED visit, level 4 ............ $1,450.00
CT scan, cervical spine ....... $890.00
X-ray, left wrist .............. $550.00

Total Charges: $2,890.00
Amount Due: $2,890.00

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
""",
    "04_ambiguous_two_clients.txt": """INTERNAL FAX COVER

Two intake forms were sent together in this transmission.

Form A - Grace Okafor, date of birth 11/02/1990.

Form B - Daniela Reyes, date of birth 05/09/1992.

Please separate and file accordingly.

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
""",
    "05_low_confidence_fax_cover.txt": """FAX COVER SHEET

To: Records Department
Re: your client Reyes
Pages: 1

Following up on the incident of 06/02/2025. Please call our office.

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
""",
    "08_okafor_insurer_letter_revised.txt": OKAFOR_LETTER.replace(
        "September 15, 2025", "September 29, 2025"
    ).replace(
        "within\nthirty days.", "within\nfourteen days. This letter replaces our earlier letter."
    ),
    "09_lindqvist_pt_note_followup.txt": """NORTHSIDE PHYSICAL THERAPY
Discharge Summary

Patient: Erik Lindqvist
DOB: 07/22/1978
Referring claim: MTA-30442

Patient met all therapy goals and is discharged to a home exercise program.

SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD
""",
}


def _pdf_escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_text_pdf(pages: list[str]) -> bytes:
    """Build a minimal, valid text PDF (Helvetica, one string per page).

    An empty string produces a page with no text, which stands in for a
    scanned image page in tests. Output is deterministic for the same input.
    """
    objects: list[bytes] = []
    kids = " ".join(f"{4 + 2 * k} 0 R" for k in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for k, text in enumerate(pages):
        if text.strip():
            ops = ["BT", "/F1 11 Tf", "14 TL", "50 750 Td"]
            ops += [f"({_pdf_escape(line)}) Tj T*" for line in text.split("\n")]
            ops.append("ET")
            stream = "\n".join(ops).encode("latin-1", errors="replace")
        else:
            stream = b""
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * k} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


def sample_upload_files() -> dict[str, bytes]:
    """All demo upload files as {filename: bytes}."""
    files = {name: text.encode("utf-8") for name, text in SAMPLE_UPLOADS.items()}
    # Byte-identical copy of the seeded MT-1001 bill -> exact duplicate.
    files["02_duplicate_reyes_er_bill.pdf"] = make_text_pdf(REYES_ER_BILL_PAGES)
    # Image-only stand-in (no text layer) -> Processing Failed.
    files["06_scanned_image_only.pdf"] = make_text_pdf([""])
    # Not a real PDF -> Processing Failed.
    files["07_corrupted_file.pdf"] = b"%PDF-1.4\nthis file was damaged in transfer\n"
    return dict(sorted(files.items()))
