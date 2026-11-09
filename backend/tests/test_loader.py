"""The enriched invoice table: row counts, joins and control flags match the data review."""

from app.data.loader import NOT_ACTIVE_STATUSES


def test_all_invoices_and_currencies_loaded(dataset):
    invoices = dataset.invoices
    assert len(invoices) == 140
    assert invoices["invoice_number"].is_unique
    assert invoices["currency"].value_counts().to_dict() == {"EUR": 89, "GBP": 27, "USD": 24}


def test_every_invoice_has_vendor_details(dataset):
    assert dataset.invoices[["country", "vendor_category", "vendor_status"]].notna().all().all()


def test_control_flag_counts(dataset):
    invoices = dataset.invoices
    assert invoices["missing_po_ref"].sum() == 21
    assert invoices["missing_required_po"].sum() == 21  # all 21 happen to be EUR 1,000 or more
    assert invoices["missing_approver"].sum() == 25
    assert (invoices["missing_po_ref"] & invoices["missing_approver"]).sum() == 3
    assert invoices["vendor_not_active"].sum() == 29
    assert invoices["is_credit_note"].sum() == 2
    assert set(invoices.loc[invoices["is_credit_note"], "invoice_number"]) == {"INV-20029", "INV-20096"}


def test_non_active_vendors_are_the_expected_two(dataset):
    not_active = dataset.invoices[dataset.invoices["vendor_status"].isin(NOT_ACTIVE_STATUSES)]
    assert set(not_active["vendor_name"]) == {"PharmaPrint Studios", "Crown Travel Partners"}


def test_missing_po_refs_include_recurring_services(dataset):
    """10 of the 21 invoices without a PO reference are cloud hosting or facilities (blanket POs, §2.3)."""
    missing = dataset.invoices[dataset.invoices["missing_po_ref"]]
    assert missing["description"].isin(["Cloud hosting", "Facilities services"]).sum() == 10


def test_lineage_fingerprints(dataset):
    assert dataset.data_snapshot.startswith("sha256:")
    assert [f.name for f in dataset.source_files] == [
        "invoices_2025_clean.csv", "vendor_master.csv", "ecb_eur_rates_2025.csv", "procurement_policy.md",
    ]
    assert all(len(f.sha256) == 64 for f in dataset.source_files)


# Override 2: a missing PO is only a breach from EUR 1,000 (§2.1).
def test_missing_po_below_eur_1000_is_not_a_breach(tmp_path):
    import shutil

    from app.config import REPO_ROOT
    from app.data.loader import load_dataset

    for name in ("invoices_2025_clean.csv", "vendor_master.csv", "ecb_eur_rates_2025.csv", "procurement_policy.md"):
        shutil.copy(REPO_ROOT / "data" / name, tmp_path / name)
    # INV-20028 is GBP 340.37 with a PO. Remove its PO number.
    path = tmp_path / "invoices_2025_clean.csv"
    path.write_text(path.read_text().replace("GBP,CC-IT-550,PO-75409,", "GBP,CC-IT-550,,"))

    invoices = load_dataset(tmp_path).invoices.set_index("invoice_number")
    assert invoices.loc["INV-20028", "missing_po_ref"]  # no PO number...
    assert not invoices.loc["INV-20028", "po_required"]  # ...but under EUR 1,000
    assert not invoices.loc["INV-20028", "missing_required_po"]  # so not a breach
    assert invoices["missing_required_po"].sum() == 21


def test_credit_notes_never_require_a_po(dataset):
    assert not dataset.invoices.loc[dataset.invoices["is_credit_note"], "po_required"].any()
